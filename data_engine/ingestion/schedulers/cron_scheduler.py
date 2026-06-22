"""Cron Scheduler — section 6.6.

APScheduler-based job scheduler for periodic channel execution.

Supports:
- Cron expressions
- Interval jobs
- One-time (date) jobs
- pause / resume / remove
- Persistent jobs via SQLite job store

Runs as a background thread — no separate process required.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.getenv("SCHEDULER_DB_URL", "sqlite:///./data/scheduler_jobs.db")
_DEFAULT_THREAD_POOL = int(os.getenv("SCHEDULER_THREADS", "4"))


class CronScheduler:
    """Manages scheduled jobs for the Hajeen data engine.

    Uses APScheduler's :class:`BackgroundScheduler` backed by a SQLite
    job store so jobs survive application restarts.

    Parameters
    ----------
    db_url:
        SQLAlchemy DB URL for the job store.
    thread_pool_size:
        Number of executor threads.
    """

    def __init__(
        self,
        db_url: str = _DEFAULT_DB,
        thread_pool_size: int = _DEFAULT_THREAD_POOL,
    ) -> None:
        self._db_url = db_url
        self._thread_pool_size = thread_pool_size
        self._scheduler: Optional[BackgroundScheduler] = None
        self._job_callbacks: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler."""
        if self._scheduler and self._scheduler.running:
            logger.warning("CronScheduler: already running")
            return

        import os
        os.makedirs("./data", exist_ok=True)

        try:
            jobstores = {
                "default": SQLAlchemyJobStore(url=self._db_url)
            }
        except Exception as exc:
            logger.warning("CronScheduler: SQLite jobstore failed (%s) — using memory", exc)
            from apscheduler.jobstores.memory import MemoryJobStore
            jobstores = {"default": MemoryJobStore()}

        executors = {
            "default": ThreadPoolExecutor(max_workers=self._thread_pool_size)
        }
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }

        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC",
        )
        self._scheduler.add_listener(self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
        self._scheduler.start()
        logger.info("CronScheduler: started (db=%s threads=%d)", self._db_url, self._thread_pool_size)

    def shutdown(self, wait: bool = True) -> None:
        """Stop the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("CronScheduler: stopped")

    @property
    def is_running(self) -> bool:
        """True when the scheduler is running."""
        return bool(self._scheduler and self._scheduler.running)

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_cron_job(
        self,
        func: Callable,
        cron_expression: str,
        job_id: str,
        name: str = "",
        args: Optional[List] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        replace_existing: bool = True,
    ) -> str:
        """Schedule a function using a cron expression.

        Parameters
        ----------
        func:
            Callable to invoke.
        cron_expression:
            Standard 5-field cron (``"0 */6 * * *"``).
        job_id:
            Unique job identifier.
        name:
            Human-readable job name.
        args / kwargs:
            Arguments forwarded to ``func``.
        replace_existing:
            If True, replaces any existing job with the same ID.

        Returns
        -------
        ``job_id``.
        """
        self._ensure_running()
        fields = cron_expression.split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression (expected 5 fields): {cron_expression!r}")

        minute, hour, dom, month, dow = fields
        trigger = CronTrigger(
            minute=minute, hour=hour,
            day=dom, month=month, day_of_week=dow,
            timezone="UTC",
        )
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=replace_existing,
        )
        logger.info("CronScheduler: added cron job id=%s expr=%r", job_id, cron_expression)
        return job_id

    def add_interval_job(
        self,
        func: Callable,
        seconds: int,
        job_id: str,
        name: str = "",
        args: Optional[List] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        replace_existing: bool = True,
    ) -> str:
        """Schedule a function at a fixed interval.

        Parameters
        ----------
        func:
            Callable to invoke.
        seconds:
            Interval in seconds.
        job_id:
            Unique job identifier.

        Returns
        -------
        ``job_id``.
        """
        self._ensure_running()
        trigger = IntervalTrigger(seconds=seconds, timezone="UTC")
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=replace_existing,
        )
        logger.info("CronScheduler: added interval job id=%s seconds=%d", job_id, seconds)
        return job_id

    def add_one_time_job(
        self,
        func: Callable,
        run_at: datetime,
        job_id: str,
        name: str = "",
        args: Optional[List] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Schedule a function to run once at a specific time.

        Parameters
        ----------
        func:
            Callable to invoke.
        run_at:
            UTC datetime when the job should run.
        job_id:
            Unique job identifier.

        Returns
        -------
        ``job_id``.
        """
        self._ensure_running()
        trigger = DateTrigger(run_date=run_at, timezone="UTC")
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or job_id,
            args=args or [],
            kwargs=kwargs or {},
        )
        logger.info("CronScheduler: added one-time job id=%s at=%s", job_id, run_at)
        return job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID.

        Returns ``True`` if found and removed.
        """
        self._ensure_running()
        try:
            self._scheduler.remove_job(job_id)
            logger.info("CronScheduler: removed job id=%s", job_id)
            return True
        except Exception:
            logger.warning("CronScheduler: job id=%s not found", job_id)
            return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        self._ensure_running()
        try:
            self._scheduler.pause_job(job_id)
            logger.info("CronScheduler: paused job id=%s", job_id)
            return True
        except Exception as exc:
            logger.warning("CronScheduler: pause failed id=%s — %s", job_id, exc)
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        self._ensure_running()
        try:
            self._scheduler.resume_job(job_id)
            logger.info("CronScheduler: resumed job id=%s", job_id)
            return True
        except Exception as exc:
            logger.warning("CronScheduler: resume failed id=%s — %s", job_id, exc)
            return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return metadata for a single job."""
        self._ensure_running()
        job = self._scheduler.get_job(job_id)
        if job is None:
            return None
        return self._job_to_dict(job)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return metadata for all scheduled jobs."""
        self._ensure_running()
        return [self._job_to_dict(j) for j in self._scheduler.get_jobs()]

    # ------------------------------------------------------------------
    # Channel scheduling helpers
    # ------------------------------------------------------------------

    def schedule_channel(
        self,
        channel_id: str,
        cron_expression: str,
        replace_existing: bool = True,
    ) -> str:
        """Schedule a channel ingestion job using a cron expression.

        Parameters
        ----------
        channel_id:
            Channel to trigger.
        cron_expression:
            Cron schedule.

        Returns
        -------
        Job ID (``f"channel_{channel_id}"``).
        """
        def _trigger_channel():
            from workers.tasks.ingestion_tasks import run_channel_ingestion
            run_channel_ingestion.delay(channel_id)

        job_id = f"channel_{channel_id}"
        return self.add_cron_job(
            func=_trigger_channel,
            cron_expression=cron_expression,
            job_id=job_id,
            name=f"Channel ingestion: {channel_id}",
            replace_existing=replace_existing,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "CronScheduler":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_running(self) -> None:
        if not self.is_running:
            self.start()

    def _on_job_event(self, event) -> None:
        if hasattr(event, "exception") and event.exception:
            logger.error(
                "CronScheduler: job FAILED id=%s error=%s",
                event.job_id, event.exception,
            )
        elif hasattr(event, "retval"):
            logger.debug("CronScheduler: job OK id=%s", event.job_id)
        else:
            logger.warning("CronScheduler: job MISSED id=%s", event.job_id)

    @staticmethod
    def _job_to_dict(job) -> Dict[str, Any]:
        next_run = job.next_run_time
        return {
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
            "trigger": str(job.trigger),
            "paused": next_run is None,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_scheduler: Optional[CronScheduler] = None


def get_scheduler() -> CronScheduler:
    """Return the module-level CronScheduler singleton."""
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = CronScheduler()
    return _default_scheduler
