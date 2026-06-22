"""Job Persistence — section 6.10.

SQLite-backed persistence for scheduled jobs and task history.

Tables:
- scheduled_jobs  — APScheduler-like job definitions
- task_history    — individual task execution records (shared with TaskMonitor)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("./data/jobs.db")


# ---------------------------------------------------------------------------
# Scheduled Job record
# ---------------------------------------------------------------------------

@dataclass
class ScheduledJob:
    """A persisted scheduled job definition."""

    job_id: str
    name: str
    channel_id: Optional[str]
    trigger_type: str                   # "cron" | "interval" | "date"
    trigger_value: str                  # cron expr, seconds, or ISO datetime
    enabled: bool = True
    last_run_at: Optional[float] = None
    next_run_at: Optional[float] = None
    run_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "channel_id": self.channel_id,
            "trigger_type": self.trigger_type,
            "trigger_value": self.trigger_value,
            "enabled": self.enabled,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "run_count": self.run_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------

class JobStore:
    """SQLite-backed store for scheduled jobs and task history.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db = db_path
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Scheduled jobs CRUD
    # ------------------------------------------------------------------

    def save_job(self, job: ScheduledJob) -> None:
        """Insert or update a scheduled job."""
        job.updated_at = time.time()
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                """INSERT INTO scheduled_jobs
                   (job_id, name, channel_id, trigger_type, trigger_value,
                    enabled, last_run_at, next_run_at, run_count, created_at,
                    updated_at, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(job_id) DO UPDATE SET
                   name=excluded.name,
                   trigger_type=excluded.trigger_type,
                   trigger_value=excluded.trigger_value,
                   enabled=excluded.enabled,
                   next_run_at=excluded.next_run_at,
                   updated_at=excluded.updated_at,
                   metadata=excluded.metadata""",
                (
                    job.job_id, job.name, job.channel_id,
                    job.trigger_type, job.trigger_value,
                    1 if job.enabled else 0,
                    job.last_run_at, job.next_run_at, job.run_count,
                    job.created_at, job.updated_at,
                    json.dumps(job.metadata),
                ),
            )
            conn.commit()
        logger.debug("JobStore: saved job_id=%s", job.job_id)

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        with sqlite3.connect(self._db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, enabled_only: bool = False) -> List[ScheduledJob]:
        with sqlite3.connect(self._db) as conn:
            conn.row_factory = sqlite3.Row
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM scheduled_jobs WHERE enabled=1 ORDER BY created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scheduled_jobs ORDER BY created_at"
                ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_job_status(
        self,
        job_id: str,
        enabled: bool,
    ) -> bool:
        with sqlite3.connect(self._db) as conn:
            cursor = conn.execute(
                "UPDATE scheduled_jobs SET enabled=?, updated_at=? WHERE job_id=?",
                (1 if enabled else 0, time.time(), job_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def record_job_run(self, job_id: str, next_run_at: Optional[float] = None) -> None:
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                """UPDATE scheduled_jobs
                   SET last_run_at=?, next_run_at=?, run_count=run_count+1, updated_at=?
                   WHERE job_id=?""",
                (time.time(), next_run_at, time.time(), job_id),
            )
            conn.commit()

    def delete_job(self, job_id: str) -> bool:
        with sqlite3.connect(self._db) as conn:
            cursor = conn.execute(
                "DELETE FROM scheduled_jobs WHERE job_id=?", (job_id,)
            )
            conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Task history
    # ------------------------------------------------------------------

    def record_task(
        self,
        task_id: str,
        task_name: str,
        status: str,
        queue: str = "default",
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> None:
        """Append a task execution record."""
        now = time.time()
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_history
                   (task_id, task_name, queue, status, created_at, duration_ms,
                    error_message, result_summary)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (task_id, task_name, queue, status, now, duration_ms, error, result_summary),
            )
            conn.commit()

    def get_task_history(
        self, task_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        with sqlite3.connect(self._db) as conn:
            conn.row_factory = sqlite3.Row
            if task_name:
                rows = conn.execute(
                    "SELECT * FROM task_history WHERE task_name=? ORDER BY created_at DESC LIMIT ?",
                    (task_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self._db) as conn:
            job_count = conn.execute("SELECT COUNT(*) FROM scheduled_jobs").fetchone()[0]
            enabled_count = conn.execute(
                "SELECT COUNT(*) FROM scheduled_jobs WHERE enabled=1"
            ).fetchone()[0]
            task_count = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
            recent_tasks = conn.execute(
                "SELECT COUNT(*) FROM task_history WHERE created_at > ?",
                (time.time() - 3600,),
            ).fetchone()[0]
        return {
            "scheduled_jobs": job_count,
            "enabled_jobs": enabled_count,
            "total_tasks": task_count,
            "tasks_last_hour": recent_tasks,
        }

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_id        TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    channel_id    TEXT,
                    trigger_type  TEXT NOT NULL,
                    trigger_value TEXT NOT NULL,
                    enabled       INTEGER DEFAULT 1,
                    last_run_at   REAL,
                    next_run_at   REAL,
                    run_count     INTEGER DEFAULT 0,
                    created_at    REAL NOT NULL,
                    updated_at    REAL NOT NULL,
                    metadata      TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id        TEXT NOT NULL,
                    task_name      TEXT NOT NULL,
                    queue          TEXT DEFAULT 'default',
                    status         TEXT NOT NULL,
                    created_at     REAL NOT NULL,
                    duration_ms    REAL,
                    error_message  TEXT,
                    result_summary TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_enabled ON scheduled_jobs (enabled)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_hist_name ON task_history (task_name)"
            )
            conn.commit()
        logger.debug("JobStore: schema ready at %s", self._db)

    @staticmethod
    def _row_to_job(row) -> ScheduledJob:
        d = dict(row)
        meta = d.get("metadata", "{}")
        return ScheduledJob(
            job_id=d["job_id"],
            name=d["name"],
            channel_id=d.get("channel_id"),
            trigger_type=d["trigger_type"],
            trigger_value=d["trigger_value"],
            enabled=bool(d["enabled"]),
            last_run_at=d.get("last_run_at"),
            next_run_at=d.get("next_run_at"),
            run_count=d.get("run_count", 0),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            metadata=json.loads(meta) if meta else {},
        )
