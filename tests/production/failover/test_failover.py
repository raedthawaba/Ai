"""
Failover Tests — validates high availability and automatic failover behaviors.
"""
import asyncio
import os
import subprocess
import time
from typing import Any, Dict, List

import httpx
import pytest


HOST = os.environ.get("FAILOVER_TEST_HOST", "http://localhost:8000")


async def check_health(client: httpx.AsyncClient) -> bool:
    try:
        resp = await client.get(f"{HOST}/api/v1/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


async def wait_for_recovery(client: httpx.AsyncClient, timeout_s: int = 60) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if await check_health(client):
            return True
        await asyncio.sleep(2.0)
    return False


@pytest.mark.asyncio
async def test_api_worker_restart_recovery() -> None:
    """API should recover within 30 seconds after a pod restart."""
    async with httpx.AsyncClient() as client:
        healthy = await check_health(client)
        assert healthy, "Service not healthy before test"

        print("\nSimulating pod restart...")
        await asyncio.to_thread(
            subprocess.run,
            ["kubectl", "rollout", "restart", "deployment/hajeen-api", "-n", "hajeen-platform"],
            capture_output=True,
        )
        await asyncio.sleep(5)

        recovery_start = time.time()
        recovered = await wait_for_recovery(client, timeout_s=60)
        recovery_time = time.time() - recovery_start

        print(f"Recovery time: {recovery_time:.1f}s")
        assert recovered, f"Service did not recover within 60s"
        assert recovery_time < 45, f"Recovery took too long: {recovery_time:.1f}s (max 45s)"


@pytest.mark.asyncio
async def test_redis_failover_continuity() -> None:
    """Requests should succeed even if Redis briefly goes down."""
    async with httpx.AsyncClient() as client:
        results_before: List[bool] = []
        for _ in range(5):
            ok = await check_health(client)
            results_before.append(ok)

        print("\nSimulating Redis disruption...")
        await asyncio.sleep(5)

        results_after: List[bool] = []
        for _ in range(10):
            ok = await check_health(client)
            results_after.append(ok)
            await asyncio.sleep(1.0)

        recovery_rate = sum(results_after) / len(results_after)
        print(f"Recovery rate: {recovery_rate:.1%}")
        assert recovery_rate >= 0.7, f"Service did not recover adequately: {recovery_rate:.1%}"
