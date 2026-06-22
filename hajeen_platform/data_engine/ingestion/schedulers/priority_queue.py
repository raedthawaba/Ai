"""Priority Queue for Ingestion Jobs — Phase 3 (Section 3.4).

قائمة انتظار ذات أولوية لمهام الـ ingestion:
- 4 مستويات أولوية: CRITICAL > HIGH > NORMAL > LOW
- Task deduplication (منع التكرار)
- Backpressure handling (رفض المهام عند امتلاء الـ queue)
- Job persistence (SQLite)
- Execution tracking
- Failed job recovery
- Concurrency control
- Queue metrics
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Priority Levels
# ─────────────────────────────────────────────────────────────────────────────

class JobPriority(IntEnum):
    """مستويات أولوية المهام (قيمة أصغر = أولوية أعلى)."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


# ─────────────────────────────────────────────────────────────────────────────
# Job Definition
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IngestionJob:
    """مهمة ingestion واحدة."""

    job_id: str
    job_type: str                          # "rss" | "api" | "crawl" | "stream"
    priority: JobPriority = JobPriority.NORMAL
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    status: str = "pending"               # pending | running | done | failed
    result: Optional[Dict] = None
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def __lt__(self, other: "IngestionJob") -> bool:
        """ترتيب حسب الأولوية ثم وقت الإنشاء."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "priority": self.priority.name,
            "status": self.status,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


@dataclass
class QueueMetrics:
    """مقاييس Priority Queue."""

    total_enqueued: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_retried: int = 0
    total_deduplicated: int = 0
    total_backpressure: int = 0
    current_size: int = 0
    running_jobs: int = 0

    def to_dict(self) -> Dict:
        return {
            "total_enqueued": self.total_enqueued,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "total_retried": self.total_retried,
            "total_deduplicated": self.total_deduplicated,
            "total_backpressure": self.total_backpressure,
            "current_size": self.current_size,
            "running_jobs": self.running_jobs,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SQLite Persistence
# ─────────────────────────────────────────────────────────────────────────────

_DB_PATH = Path("./data/ingestion_jobs.db")
_DB_LOCK = threading.RLock()


def _ensure_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_jobs (
            job_id       TEXT PRIMARY KEY,
            job_type     TEXT NOT NULL,
            priority     INTEGER NOT NULL DEFAULT 2,
            payload_json TEXT,
            status       TEXT NOT NULL DEFAULT 'pending',
            retry_count  INTEGER DEFAULT 0,
            max_retries  INTEGER DEFAULT 3,
            error        TEXT,
            created_at   TEXT,
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


def _persist_job(job: IngestionJob) -> None:
    with _DB_LOCK:
        try:
            conn = _ensure_db()
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_jobs
                (job_id, job_type, priority, payload_json, status,
                 retry_count, max_retries, error, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id, job.job_type, int(job.priority),
                json.dumps(job.payload, ensure_ascii=False),
                job.status, job.retry_count, job.max_retries,
                job.error,
                job.created_at.isoformat(),
                job.completed_at.isoformat() if job.completed_at else None,
            ))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("_persist_job: error — %s", exc)


def _load_pending_jobs() -> List[IngestionJob]:
    """استرجاع المهام المعلّقة عند بدء التشغيل."""
    with _DB_LOCK:
        try:
            conn = _ensure_db()
            rows = conn.execute(
                "SELECT job_id, job_type, priority, payload_json, retry_count, "
                "max_retries, created_at FROM ingestion_jobs WHERE status='pending'"
            ).fetchall()
            conn.close()

            jobs = []
            for row in rows:
                try:
                    payload = json.loads(row[3] or "{}")
                    created = datetime.fromisoformat(row[6]) if row[6] else datetime.now(timezone.utc)
                    jobs.append(IngestionJob(
                        job_id=row[0],
                        job_type=row[1],
                        priority=JobPriority(row[2]),
                        payload=payload,
                        retry_count=row[4],
                        max_retries=row[5],
                        created_at=created,
                    ))
                except Exception as exc:
                    logger.warning("_load_pending_jobs: error parsing job — %s", exc)
            return jobs
        except Exception as exc:
            logger.error("_load_pending_jobs: DB error — %s", exc)
            return []


# ─────────────────────────────────────────────────────────────────────────────
# IngestionPriorityQueue
# ─────────────────────────────────────────────────────────────────────────────

class IngestionPriorityQueue:
    """قائمة انتظار ذات أولوية لمهام الـ ingestion.

    Parameters
    ----------
    max_size:
        الحجم الأقصى للـ queue (backpressure).
    max_concurrent:
        عدد المهام المتزامنة.
    persist:
        هل نحفظ المهام في SQLite؟
    """

    def __init__(
        self,
        max_size: int = 1000,
        max_concurrent: int = 10,
        persist: bool = True,
    ) -> None:
        self.max_size = max_size
        self.max_concurrent = max_concurrent
        self.persist = persist
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._running: Dict[str, IngestionJob] = {}
        self._seen_ids: set = set()  # deduplication
        self._lock = asyncio.Lock()
        self.metrics = QueueMetrics()

    # ─── Public API ─────────────────────────────────────────────────────

    async def enqueue(
        self,
        job_type: str,
        payload: Dict[str, Any],
        priority: JobPriority = JobPriority.NORMAL,
        job_id: Optional[str] = None,
        max_retries: int = 3,
        tags: Optional[List[str]] = None,
    ) -> Optional[IngestionJob]:
        """إضافة مهمة للـ queue.

        Parameters
        ----------
        job_type:
            نوع المهمة.
        payload:
            بيانات المهمة.
        priority:
            الأولوية.
        job_id:
            معرّف مخصص (None = تلقائي).

        Returns
        -------
        IngestionJob إذا نجحت الإضافة، None إذا رُفضت (dedup/backpressure).
        """
        effective_id = job_id or str(uuid.uuid4())[:8]

        async with self._lock:
            # Deduplication
            if effective_id in self._seen_ids:
                self.metrics.total_deduplicated += 1
                logger.debug("IngestionPriorityQueue: duplicate job_id=%s", effective_id)
                return None

            # Backpressure
            if self._queue.full():
                self.metrics.total_backpressure += 1
                logger.warning(
                    "IngestionPriorityQueue: queue full (max=%d) — rejecting job_type=%s",
                    self.max_size, job_type,
                )
                return None

            job = IngestionJob(
                job_id=effective_id,
                job_type=job_type,
                priority=priority,
                payload=payload,
                max_retries=max_retries,
                tags=tags or [],
            )

            self._seen_ids.add(effective_id)
            self.metrics.total_enqueued += 1
            self.metrics.current_size = self._queue.qsize() + 1

        # الإضافة للـ priority queue
        await self._queue.put((int(priority), time.monotonic(), job))

        if self.persist:
            _persist_job(job)

        logger.debug(
            "IngestionPriorityQueue: enqueued job_id=%s type=%s priority=%s",
            effective_id, job_type, priority.name,
        )
        return job

    async def dequeue(self, timeout_s: float = 5.0) -> Optional[IngestionJob]:
        """سحب أولى مهمة من الـ queue.

        Returns
        -------
        IngestionJob أو None عند timeout.
        """
        if len(self._running) >= self.max_concurrent:
            logger.debug(
                "IngestionPriorityQueue: max_concurrent=%d reached", self.max_concurrent
            )
            await asyncio.sleep(0.5)
            return None

        try:
            _, _, job = await asyncio.wait_for(
                self._queue.get(), timeout=timeout_s
            )
            async with self._lock:
                job.status = "running"
                self._running[job.job_id] = job
                self.metrics.current_size = self._queue.qsize()
                self.metrics.running_jobs = len(self._running)
            if self.persist:
                _persist_job(job)
            return job
        except asyncio.TimeoutError:
            return None

    async def complete(self, job: IngestionJob, result: Optional[Dict] = None) -> None:
        """تمييز مهمة كمكتملة."""
        async with self._lock:
            job.status = "done"
            job.result = result
            job.completed_at = datetime.now(timezone.utc)
            self._running.pop(job.job_id, None)
            self.metrics.total_completed += 1
            self.metrics.running_jobs = len(self._running)
        if self.persist:
            _persist_job(job)

    async def fail(self, job: IngestionJob, error: str) -> bool:
        """تمييز مهمة كفاشلة مع إمكانية إعادة المحاولة.

        Returns
        -------
        True إذا أُعيدت للـ queue، False إذا وصلت للحد الأقصى.
        """
        async with self._lock:
            self._running.pop(job.job_id, None)
            self.metrics.running_jobs = len(self._running)

        job.error = error
        job.retry_count += 1

        if job.retry_count <= job.max_retries:
            # إعادة المحاولة بأولوية أقل
            new_priority = min(int(job.priority) + 1, int(JobPriority.LOW))
            job.priority = JobPriority(new_priority)
            job.status = "pending"
            self.metrics.total_retried += 1
            logger.warning(
                "IngestionPriorityQueue: retry job_id=%s attempt=%d/%d",
                job.job_id, job.retry_count, job.max_retries,
            )
            await self._queue.put((int(job.priority), time.monotonic(), job))
            if self.persist:
                _persist_job(job)
            return True
        else:
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            self.metrics.total_failed += 1
            logger.error(
                "IngestionPriorityQueue: job FAILED job_id=%s error=%s",
                job.job_id, error,
            )
            if self.persist:
                _persist_job(job)
            return False

    async def restore_from_db(self) -> int:
        """استعادة المهام المعلّقة من SQLite."""
        if not self.persist:
            return 0
        jobs = _load_pending_jobs()
        restored = 0
        for job in jobs:
            result = await self.enqueue(
                job_type=job.job_type,
                payload=job.payload,
                priority=job.priority,
                job_id=job.job_id,
                max_retries=job.max_retries,
            )
            if result:
                restored += 1
        logger.info("IngestionPriorityQueue: restored %d jobs from DB", restored)
        return restored

    def get_metrics(self) -> QueueMetrics:
        self.metrics.current_size = self._queue.qsize()
        self.metrics.running_jobs = len(self._running)
        return self.metrics

    def get_running_jobs(self) -> List[IngestionJob]:
        return list(self._running.values())

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_full(self) -> bool:
        return self._queue.full()

    @property
    def is_empty(self) -> bool:
        return self._queue.empty()
