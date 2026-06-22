"""Resource Guard — Phase 7 — حماية الموارد من الاستنزاف."""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import signal
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Callable, Generator, Optional

logger = logging.getLogger(__name__)


class MemoryGuard:
    """مراقبة الذاكرة ومنع الاستنزاف."""

    def __init__(self, max_memory_mb: float = 4096.0) -> None:
        self._max_mb = max_memory_mb
        self._start_mb = self._current_mb()

    def _current_mb(self) -> float:
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0

    def check(self) -> bool:
        current = self._current_mb()
        if current > self._max_mb:
            logger.warning(
                "تجاوز حد الذاكرة: %.1f MB > %.1f MB", current, self._max_mb
            )
            return False
        return True

    def memory_delta_mb(self) -> float:
        return self._current_mb() - self._start_mb

    @contextmanager
    def guard(self) -> Generator:
        if not self.check():
            raise MemoryError(f"الذاكرة تتجاوز الحد: {self._max_mb} MB")
        try:
            yield
        finally:
            delta = self.memory_delta_mb()
            if delta > 100:
                logger.warning("تسرّب ذاكرة محتمل: +%.1f MB", delta)


class TimeoutGuard:
    """تطبيق timeout على العمليات الطويلة."""

    @staticmethod
    @asynccontextmanager
    async def async_timeout(seconds: float, name: str = "operation") -> AsyncGenerator:
        try:
            async with asyncio.timeout(seconds):
                yield
        except asyncio.TimeoutError:
            logger.error("Timeout: '%s' تجاوز %.1fs", name, seconds)
            raise TimeoutError(f"العملية '{name}' تجاوزت {seconds}s") from None

    @staticmethod
    @contextmanager
    def sync_timeout(seconds: float, name: str = "operation") -> Generator:
        """Timeout للعمليات المتزامنة (Unix only)."""
        def _handler(signum: int, frame: Any) -> None:
            raise TimeoutError(f"العملية '{name}' تجاوزت {seconds}s")

        old = signal.signal(signal.SIGALRM, _handler) if hasattr(signal, "SIGALRM") else None
        try:
            if hasattr(signal, "alarm"):
                signal.alarm(int(seconds))
            yield
        finally:
            if hasattr(signal, "alarm"):
                signal.alarm(0)
            if old is not None:
                signal.signal(signal.SIGALRM, old)


class RequestThrottler:
    """تقييد معدل الطلبات المتزامنة."""

    def __init__(self, max_concurrent: int = 10) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent
        self._current = 0
        self._lock = threading.Lock()

    @property
    def current_count(self) -> int:
        return self._current

    @asynccontextmanager
    async def throttle(self) -> AsyncGenerator:
        with self._lock:
            self._current += 1
        try:
            async with self._sem:
                yield
        finally:
            with self._lock:
                self._current -= 1

    def is_overloaded(self) -> bool:
        return self._current >= self._max


class WorkerIsolation:
    """
    Worker isolation — يُشغّل المهام في executor منفصل
    مع حماية من الانهيار.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._max = max_workers
        self._executor: Optional[Any] = None

    def _get_executor(self) -> Any:
        if self._executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self._executor = ThreadPoolExecutor(max_workers=self._max)
        return self._executor

    async def run(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        partial_fn = functools.partial(fn, *args, **kwargs)
        return await loop.run_in_executor(self._get_executor(), partial_fn)

    def shutdown(self, wait: bool = True) -> None:
        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None


class GracefulDegradation:
    """
    تدهور رشيق — يُعيد fallback عند فشل العملية الأساسية.
    """

    def __init__(self, fallback: Any = None, max_failures: int = 5) -> None:
        self._fallback = fallback
        self._max_failures = max_failures
        self._failure_count = 0
        self._last_failure: Optional[float] = None
        self._recovery_window = 60.0  # ثانية

    def is_open(self) -> bool:
        """Circuit breaker — مفتوح = الدائرة مكسورة."""
        if self._failure_count < self._max_failures:
            return False
        if self._last_failure and time.time() - self._last_failure > self._recovery_window:
            self._failure_count = 0
            return False
        return True

    def record_success(self) -> None:
        self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure = time.time()
        if self.is_open():
            logger.error(
                "Circuit breaker مفتوح: %d failures", self._failure_count
            )

    @asynccontextmanager
    async def guard(self) -> AsyncGenerator:
        if self.is_open():
            logger.warning("Circuit breaker مفتوح — إعادة الـ fallback")
            yield self._fallback
            return
        try:
            yield None
            self.record_success()
        except Exception as exc:
            self.record_failure()
            logger.error("فشل محمي بـ circuit breaker: %s", exc)
            if self._fallback is not None:
                yield self._fallback
            else:
                raise


class ResourceGuard:
    """
    Orchestrator لجميع آليات الحماية.
    """

    def __init__(
        self,
        max_memory_mb: float = 4096.0,
        max_concurrent: int = 10,
        max_workers: int = 4,
        request_timeout: float = 30.0,
    ) -> None:
        self.memory = MemoryGuard(max_memory_mb)
        self.throttler = RequestThrottler(max_concurrent)
        self.isolation = WorkerIsolation(max_workers)
        self.timeout_seconds = request_timeout
        logger.info(
            "ResourceGuard: memory=%.0fMB concurrent=%d workers=%d timeout=%.0fs",
            max_memory_mb, max_concurrent, max_workers, request_timeout,
        )

    @asynccontextmanager
    async def protected_request(self, name: str = "request") -> AsyncGenerator:
        """Context manager يطبق جميع الحمايات."""
        if not self.memory.check():
            raise MemoryError("ذاكرة النظام منخفضة")

        async with self.throttler.throttle():
            async with TimeoutGuard.async_timeout(self.timeout_seconds, name):
                yield

    def health(self) -> dict:
        return {
            "memory_current_mb": round(self.memory._current_mb(), 1),
            "memory_limit_mb": self.memory._max_mb,
            "concurrent_requests": self.throttler.current_count,
            "overloaded": self.throttler.is_overloaded(),
            "timeout_s": self.timeout_seconds,
        }
