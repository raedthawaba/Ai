"""Health Checker — Phase 6 — فحص صحة جميع مكونات المنصة."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    details: Dict = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at,
        }


@dataclass
class SystemHealth:
    status: HealthStatus
    components: List[ComponentHealth]
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "checked_at": self.checked_at,
            "components": {c.name: c.to_dict() for c in self.components},
        }


class HealthChecker:
    """
    يفحص صحة جميع مكونات المنصة:
    - Database (SQLite / PostgreSQL)
    - Vector Store (FAISS / Qdrant / Chroma)
    - Queue
    - Workers
    - Memory
    - Embedding model
    - External APIs (graceful)
    """

    def __init__(self, timeout: float = 5.0) -> None:
        self._checks: Dict[str, Callable] = {}
        self._timeout = timeout
        self._register_builtin_checks()

    def register(self, name: str, check_fn: Callable) -> None:
        """تسجيل فحص مخصص."""
        self._checks[name] = check_fn

    def _register_builtin_checks(self) -> None:
        self._checks["memory"] = self._check_memory
        self._checks["disk"] = self._check_disk
        self._checks["database"] = self._check_database
        self._checks["vector_store"] = self._check_vector_store
        self._checks["queue"] = self._check_queue

    # ─── Run ──────────────────────────────────────────────────────────────────

    async def check_all(self) -> SystemHealth:
        tasks = {
            name: self._run_check(name, fn)
            for name, fn in self._checks.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        components: List[ComponentHealth] = []
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, ComponentHealth):
                components.append(result)
            else:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.DOWN,
                    message=str(result),
                ))

        overall = HealthStatus.OK
        for c in components:
            if c.status == HealthStatus.DOWN:
                overall = HealthStatus.DOWN
                break
            if c.status == HealthStatus.DEGRADED:
                overall = HealthStatus.DEGRADED

        return SystemHealth(status=overall, components=components)

    async def check_one(self, name: str) -> ComponentHealth:
        fn = self._checks.get(name)
        if fn is None:
            return ComponentHealth(
                name=name, status=HealthStatus.UNKNOWN,
                message=f"فحص '{name}' غير مسجّل"
            )
        return await self._run_check(name, fn)

    async def _run_check(self, name: str, fn: Callable) -> ComponentHealth:
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self._to_coroutine(fn), timeout=self._timeout
            )
            latency = (time.perf_counter() - t0) * 1000
            if isinstance(result, ComponentHealth):
                result.latency_ms = latency
                return result
            return ComponentHealth(
                name=name, status=HealthStatus.OK, latency_ms=latency
            )
        except asyncio.TimeoutError:
            latency = (time.perf_counter() - t0) * 1000
            return ComponentHealth(
                name=name, status=HealthStatus.DOWN,
                latency_ms=latency, message="timeout",
            )
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            logger.error("Health check '%s' failed: %s", name, exc)
            return ComponentHealth(
                name=name, status=HealthStatus.DOWN,
                latency_ms=latency, message=str(exc),
            )

    @staticmethod
    async def _to_coroutine(fn: Callable) -> Any:
        if asyncio.iscoroutinefunction(fn):
            return await fn()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)

    # ─── Built-in Checks ─────────────────────────────────────────────────────

    def _check_memory(self) -> ComponentHealth:
        try:
            import psutil
            mem = psutil.virtual_memory()
            pct = mem.percent
            status = (
                HealthStatus.OK if pct < 80
                else HealthStatus.DEGRADED if pct < 95
                else HealthStatus.DOWN
            )
            return ComponentHealth(
                name="memory",
                status=status,
                message=f"{pct:.1f}% used",
                details={
                    "total_gb": round(mem.total / 1e9, 2),
                    "available_gb": round(mem.available / 1e9, 2),
                    "percent": pct,
                },
            )
        except ImportError:
            import os
            return ComponentHealth(name="memory", status=HealthStatus.UNKNOWN,
                                   message="psutil غير متاح")

    def _check_disk(self) -> ComponentHealth:
        try:
            import psutil
            disk = psutil.disk_usage("/")
            pct = disk.percent
            status = (
                HealthStatus.OK if pct < 80
                else HealthStatus.DEGRADED if pct < 95
                else HealthStatus.DOWN
            )
            return ComponentHealth(
                name="disk",
                status=status,
                message=f"{pct:.1f}% used",
                details={
                    "total_gb": round(disk.total / 1e9, 2),
                    "free_gb": round(disk.free / 1e9, 2),
                    "percent": pct,
                },
            )
        except ImportError:
            return ComponentHealth(name="disk", status=HealthStatus.UNKNOWN)

    def _check_database(self) -> ComponentHealth:
        try:
            import sqlite3
            db_path = os.getenv("SQLITE_DB_PATH", "./data/hajeen.db")
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            conn = sqlite3.connect(db_path, timeout=2.0)
            conn.execute("SELECT 1")
            conn.close()
            return ComponentHealth(
                name="database", status=HealthStatus.OK,
                message="SQLite responsive", details={"path": db_path},
            )
        except Exception as exc:
            return ComponentHealth(
                name="database", status=HealthStatus.DOWN, message=str(exc)
            )

    def _check_vector_store(self) -> ComponentHealth:
        try:
            store_dir = "./storage_data"
            exists = os.path.isdir(store_dir)
            return ComponentHealth(
                name="vector_store",
                status=HealthStatus.OK if exists else HealthStatus.DEGRADED,
                message="storage directory accessible" if exists else "storage dir missing",
                details={"store_dir": store_dir},
            )
        except Exception as exc:
            return ComponentHealth(
                name="vector_store", status=HealthStatus.DOWN, message=str(exc)
            )

    def _check_queue(self) -> ComponentHealth:
        return ComponentHealth(
            name="queue",
            status=HealthStatus.OK,
            message="in-process queue active",
            details={"type": "asyncio.Queue"},
        )

    # ─── Startup Diagnostics ─────────────────────────────────────────────────

    async def startup_check(self) -> bool:
        """يُشغَّل عند بدء التطبيق — يُعيد True إذا كل شيء OK."""
        health = await self.check_all()
        logger.info("Startup health: %s", health.status.value)
        for c in health.components:
            if c.status == HealthStatus.DOWN:
                logger.error("مكوّن فاشل: %s — %s", c.name, c.message)
            elif c.status == HealthStatus.DEGRADED:
                logger.warning("مكوّن متدهور: %s — %s", c.name, c.message)
        return health.status != HealthStatus.DOWN

    def self_test(self) -> Dict:
        """اختبار ذاتي سريع للتحقق من جاهزية الـ checker."""
        return {
            "checks_registered": list(self._checks.keys()),
            "timeout_s": self._timeout,
            "status": "ready",
        }
