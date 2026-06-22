"""
Stress Tests — pushes the system beyond normal load to identify breaking points.
"""
import asyncio
import os
import time
from typing import Any, Dict, List

import httpx
import pytest


class StressTestConfig:
    HOST = os.environ.get("STRESS_TEST_HOST", "http://localhost:8000")
    MAX_CONCURRENT = int(os.environ.get("STRESS_MAX_CONCURRENT", "500"))
    RAMP_DURATION_S = int(os.environ.get("STRESS_RAMP_S", "60"))
    SUSTAINED_DURATION_S = int(os.environ.get("STRESS_SUSTAINED_S", "120"))
    HEADERS = {"Content-Type": "application/json", "X-Tenant-ID": "stress-test"}


async def fire_request(client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    async with semaphore:
        start = time.perf_counter()
        try:
            resp = await client.post(
                f"{StressTestConfig.HOST}/api/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 50},
                headers=StressTestConfig.HEADERS,
                timeout=30.0,
            )
            return {
                "status": resp.status_code,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "success": resp.status_code in (200, 429),
            }
        except Exception as exc:
            return {
                "status": 0,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "success": False,
                "error": str(exc),
            }


@pytest.mark.asyncio
async def test_concurrent_requests_1000() -> None:
    """Validate system handles 1000 concurrent requests without complete failure."""
    N = 1000
    semaphore = asyncio.Semaphore(StressTestConfig.MAX_CONCURRENT)
    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        tasks = [fire_request(client, semaphore) for _ in range(N)]
        results = await asyncio.gather(*tasks)

    total = len(results)
    success = sum(1 for r in results if r["success"])
    failure_rate = (total - success) / total
    latencies = [r["latency_ms"] for r in results]
    latencies.sort()
    p99 = latencies[int(len(latencies) * 0.99)]

    print(f"\nStress Test Results ({N} concurrent requests):")
    print(f"  Success rate: {success/total:.1%}")
    print(f"  P99 latency: {p99:.0f}ms")
    print(f"  Failure rate: {failure_rate:.1%}")

    assert failure_rate < 0.20, f"Too many failures under stress: {failure_rate:.1%} (max 20%)"
    assert p99 < 30000, f"P99 latency too high: {p99:.0f}ms (max 30000ms)"


@pytest.mark.asyncio
async def test_memory_leak_detection() -> None:
    """Run sustained load and verify memory doesn't grow unboundedly."""
    import psutil
    proc = psutil.Process(os.getpid())

    initial_memory_mb = proc.memory_info().rss / 1024 / 1024
    N_BATCHES = 10
    BATCH_SIZE = 50

    semaphore = asyncio.Semaphore(50)
    async with httpx.AsyncClient() as client:
        for batch in range(N_BATCHES):
            tasks = [fire_request(client, semaphore) for _ in range(BATCH_SIZE)]
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.5)

    final_memory_mb = proc.memory_info().rss / 1024 / 1024
    growth_mb = final_memory_mb - initial_memory_mb

    print(f"\nMemory: initial={initial_memory_mb:.0f}MB, final={final_memory_mb:.0f}MB, growth={growth_mb:.0f}MB")
    assert growth_mb < 500, f"Memory leak detected: grew by {growth_mb:.0f}MB"


@pytest.mark.asyncio
async def test_graceful_degradation() -> None:
    """Verify system degrades gracefully under extreme load (returns 429, not 500)."""
    N = 2000
    semaphore = asyncio.Semaphore(StressTestConfig.MAX_CONCURRENT)

    async with httpx.AsyncClient() as client:
        tasks = [fire_request(client, semaphore) for _ in range(N)]
        results = await asyncio.gather(*tasks)

    server_errors = sum(1 for r in results if r["status"] >= 500 and r["status"] != 503)
    too_many_requests = sum(1 for r in results if r["status"] == 429)
    rate = server_errors / N

    print(f"\nGraceful degradation: {too_many_requests} rate-limited, {server_errors} server errors")
    assert rate < 0.05, f"Too many server errors under extreme load: {rate:.1%}"
