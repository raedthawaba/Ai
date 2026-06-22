"""Phase 8.3 — Queue Manager: إدارة طابور طلبات الـ inference."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .request_handler import InferenceJob, JobStatus

logger = logging.getLogger(__name__)


@dataclass
class QueueStats:
    """إحصائيات طابور الطلبات."""
    total_queued: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    current_queue_size: int = 0
    active_jobs: int = 0
    avg_wait_ms: float = 0.0
    avg_exec_ms: float = 0.0


class QueueManager:
    """
    إدارة طابور طلبات الـ inference.

    المهام:
    - تنظيم طابور حسب الأولوية
    - التحكم في التزامن
    - إلغاء الطلبات
    - إحصائيات مستمرة
    - Backpressure handling
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        max_queue_size: int = 100,
        job_timeout: float = 120.0,
    ):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.job_timeout = job_timeout

        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._active_jobs: Dict[str, InferenceJob] = {}
        self._completed_jobs: Dict[str, InferenceJob] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None

        self._total_queued = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_cancelled = 0
        self._wait_times: List[float] = []
        self._exec_times: List[float] = []

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    async def submit(self, job: InferenceJob) -> str:
        """إضافة job للطابور."""
        if self._queue.full():
            raise RuntimeError(
                f"Queue is full ({self.max_queue_size} jobs). "
                "Try again later."
            )

        job.status = JobStatus.PENDING
        # Priority queue: أصغر رقم = أولوية أعلى
        priority_key = (10 - job.priority, job.created_at)
        await self._queue.put((priority_key, job))
        self._total_queued += 1

        logger.debug("Job queued: %s (priority=%d)", job.job_id, job.priority)
        return job.job_id

    async def process_job(
        self,
        job: InferenceJob,
        executor: Callable,
    ) -> InferenceJob:
        """تنفيذ job واحد مع Semaphore control."""
        semaphore = self._get_semaphore()

        async with semaphore:
            if job.cancelled:
                return job

            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            self._active_jobs[job.job_id] = job

            wait_ms = job.wait_time_ms
            self._wait_times.append(wait_ms)

            try:
                job.result = await asyncio.wait_for(
                    executor(job.request),
                    timeout=self.job_timeout,
                )
                job.status = JobStatus.COMPLETED
                self._total_completed += 1

            except asyncio.TimeoutError:
                job.status = JobStatus.TIMEOUT
                job.error = f"Job timed out after {self.job_timeout}s"
                self._total_failed += 1
                logger.warning("Job timeout: %s", job.job_id)

            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                self._total_cancelled += 1

            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                self._total_failed += 1
                logger.error("Job failed %s: %s", job.job_id, e)

            finally:
                job.completed_at = time.time()
                exec_ms = job.execution_time_ms
                self._exec_times.append(exec_ms)
                self._active_jobs.pop(job.job_id, None)
                self._completed_jobs[job.job_id] = job

        return job

    async def run_worker(self, executor: Callable) -> None:
        """Worker loop — يُنفّذ jobs من الطابور."""
        logger.info("Queue worker started (max_concurrent=%d)", self.max_concurrent)
        while True:
            try:
                _, job = await self._queue.get()
                if job.cancelled:
                    self._queue.task_done()
                    continue
                asyncio.create_task(self.process_job(job, executor))
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker error: %s", e)

    def get_job(self, job_id: str) -> Optional[InferenceJob]:
        return (
            self._active_jobs.get(job_id)
            or self._completed_jobs.get(job_id)
        )

    def cancel_job(self, job_id: str) -> bool:
        job = self._active_jobs.get(job_id)
        if job:
            job.cancel()
            self._total_cancelled += 1
            return True
        return False

    def get_stats(self) -> QueueStats:
        avg_wait = (
            sum(self._wait_times[-100:]) / len(self._wait_times[-100:])
            if self._wait_times else 0.0
        )
        avg_exec = (
            sum(self._exec_times[-100:]) / len(self._exec_times[-100:])
            if self._exec_times else 0.0
        )
        return QueueStats(
            total_queued=self._total_queued,
            total_completed=self._total_completed,
            total_failed=self._total_failed,
            total_cancelled=self._total_cancelled,
            current_queue_size=self._queue.qsize(),
            active_jobs=len(self._active_jobs),
            avg_wait_ms=round(avg_wait, 2),
            avg_exec_ms=round(avg_exec, 2),
        )
