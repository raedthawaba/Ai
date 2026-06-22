"""Task Monitor — section 6.9.

Monitors running, failed, and completed tasks. Stores metrics in SQLite.

Tracks:
- Running tasks
- Failed tasks
- Retries
- Execution times
- Queue sizes
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("./data/task_monitor.db")


class TaskStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    RETRYING  = "retrying"
    CANCELLED = "cancelled"
    DEAD      = "dead"


@dataclass
class TaskRecord:
    """A single task execution record."""

    task_id: str
    task_name: str
    queue: str = "default"
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    attempts: int = 0
    last_error: Optional[str] = None
    result_summary: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at) * 1000, 2)
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "queue": self.queue,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "result_summary": self.result_summary,
            "created_at": self.created_at,
        }
        return d


class TaskMonitor:
    """SQLite-backed task execution monitor.

    Parameters
    ----------
    db_path:
        Path to the SQLite monitoring database.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._ensure_db()

    # ------------------------------------------------------------------
    # Lifecycle events
    # ------------------------------------------------------------------

    def on_task_start(
        self,
        task_id: str,
        task_name: str,
        queue: str = "default",
    ) -> TaskRecord:
        """Record task start."""
        record = TaskRecord(
            task_id=task_id,
            task_name=task_name,
            queue=queue,
            status=TaskStatus.RUNNING,
            started_at=time.time(),
            attempts=1,
        )
        self._upsert(record)
        logger.debug("TaskMonitor: START id=%s name=%s", task_id, task_name)
        return record

    def on_task_success(
        self,
        task_id: str,
        result_summary: Optional[str] = None,
    ) -> None:
        """Record task success."""
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE task_history
                   SET status=?, finished_at=?, result_summary=?
                   WHERE task_id=?""",
                (TaskStatus.SUCCESS.value, now, result_summary, task_id),
            )
            conn.commit()
        logger.debug("TaskMonitor: SUCCESS id=%s", task_id)

    def on_task_failure(
        self,
        task_id: str,
        error: str,
        is_dead: bool = False,
    ) -> None:
        """Record task failure or death."""
        now = time.time()
        status = TaskStatus.DEAD if is_dead else TaskStatus.FAILED
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE task_history
                   SET status=?, finished_at=?, last_error=?, attempts=attempts+1
                   WHERE task_id=?""",
                (status.value, now, error[:500], task_id),
            )
            conn.commit()
        log_fn = logger.error if is_dead else logger.warning
        log_fn("TaskMonitor: %s id=%s error=%s", status.value.upper(), task_id, error[:100])

    def on_task_retry(self, task_id: str, error: str) -> None:
        """Record a retry attempt."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE task_history
                   SET status=?, last_error=?, attempts=attempts+1
                   WHERE task_id=?""",
                (TaskStatus.RETRYING.value, error[:500], task_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return a task record by ID."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM task_history WHERE task_id=?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def running_tasks(self) -> List[Dict[str, Any]]:
        """Return all currently running tasks."""
        return self._query_status(TaskStatus.RUNNING)

    def failed_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent failed / dead tasks."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_history WHERE status IN (?,?) "
                "ORDER BY finished_at DESC LIMIT ?",
                (TaskStatus.FAILED.value, TaskStatus.DEAD.value, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def retrying_tasks(self) -> List[Dict[str, Any]]:
        return self._query_status(TaskStatus.RETRYING)

    def summary(self) -> Dict[str, Any]:
        """Return a monitoring dashboard summary."""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
            by_status = conn.execute(
                "SELECT status, COUNT(*) FROM task_history GROUP BY status"
            ).fetchall()
            avg_duration = conn.execute(
                "SELECT AVG((finished_at - started_at) * 1000) FROM task_history "
                "WHERE status=? AND finished_at IS NOT NULL",
                (TaskStatus.SUCCESS.value,),
            ).fetchone()[0]
            recent = conn.execute(
                "SELECT COUNT(*) FROM task_history WHERE created_at > ?",
                (time.time() - 3600,),
            ).fetchone()[0]

        return {
            "total_tasks": total,
            "tasks_last_hour": recent,
            "avg_duration_ms": round(avg_duration, 2) if avg_duration else None,
            "by_status": {r[0]: r[1] for r in by_status},
        }

    def slow_tasks(self, threshold_ms: float = 5000, limit: int = 10) -> List[Dict[str, Any]]:
        """Return tasks that exceeded the duration threshold."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT *, (finished_at - started_at)*1000 AS duration_ms "
                "FROM task_history "
                "WHERE finished_at IS NOT NULL AND (finished_at - started_at)*1000 > ? "
                "ORDER BY duration_ms DESC LIMIT ?",
                (threshold_ms, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id         TEXT NOT NULL UNIQUE,
                    task_name       TEXT NOT NULL,
                    queue           TEXT DEFAULT 'default',
                    status          TEXT NOT NULL,
                    started_at      REAL,
                    finished_at     REAL,
                    attempts        INTEGER DEFAULT 1,
                    last_error      TEXT,
                    result_summary  TEXT,
                    created_at      REAL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status ON task_history (status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created ON task_history (created_at)"
            )
            conn.commit()

    def _upsert(self, record: TaskRecord) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO task_history
                   (task_id, task_name, queue, status, started_at, finished_at,
                    attempts, last_error, result_summary, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(task_id) DO UPDATE SET
                   status=excluded.status,
                   started_at=COALESCE(task_history.started_at, excluded.started_at),
                   attempts=task_history.attempts+1""",
                (
                    record.task_id, record.task_name, record.queue,
                    record.status.value, record.started_at, record.finished_at,
                    record.attempts, record.last_error, record.result_summary,
                    record.created_at,
                ),
            )
            conn.commit()

    def _query_status(self, status: TaskStatus) -> List[Dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_history WHERE status=? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
            return [dict(r) for r in rows]
