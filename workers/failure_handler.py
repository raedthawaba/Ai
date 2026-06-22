"""Failure Handler — section 6.8.

Centralised failure tracking and dead-letter queue for tasks.

Features:
- Records failures with full context
- Alerts on repeated failures
- Dead letter queue (SQLite-backed)
- Failure statistics
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("./data/failures.db")


@dataclass
class TaskFailure:
    """A single recorded task failure."""

    task_id: str
    task_name: str
    error_type: str
    error_message: str
    attempt: int
    timestamp: float = field(default_factory=time.time)
    payload: Optional[Dict[str, Any]] = None
    is_dead: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.payload:
            d["payload"] = json.dumps(self.payload)
        return d


class FailureHandler:
    """Records and manages task failures in a SQLite dead-letter store.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.
    max_retries_before_dead:
        After this many failures, a task is marked as dead.
    alert_threshold:
        Log an ALERT when total dead tasks exceeds this number.
    """

    def __init__(
        self,
        db_path: Path = _DEFAULT_DB,
        max_retries_before_dead: int = 3,
        alert_threshold: int = 10,
    ) -> None:
        self._db_path = db_path
        self.max_retries_before_dead = max_retries_before_dead
        self.alert_threshold = alert_threshold
        self._ensure_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_failure(
        self,
        task_id: str,
        task_name: str,
        error: Exception,
        attempt: int,
        payload: Optional[Dict[str, Any]] = None,
    ) -> TaskFailure:
        """Record a task failure.

        Parameters
        ----------
        task_id:
            Celery task ID.
        task_name:
            Task function name.
        error:
            Exception that caused the failure.
        attempt:
            Attempt number (1-indexed).
        payload:
            Optional task arguments for debugging.

        Returns
        -------
        :class:`TaskFailure`.
        """
        is_dead = attempt >= self.max_retries_before_dead
        failure = TaskFailure(
            task_id=task_id,
            task_name=task_name,
            error_type=type(error).__name__,
            error_message=str(error)[:500],
            attempt=attempt,
            payload=payload,
            is_dead=is_dead,
        )
        self._insert_failure(failure)

        if is_dead:
            logger.error(
                "FailureHandler: DEAD task id=%s name=%s after %d attempts: %s",
                task_id, task_name, attempt, error,
            )
            self._check_alert_threshold()
        else:
            logger.warning(
                "FailureHandler: task FAILED id=%s name=%s attempt=%d: %s",
                task_id, task_name, attempt, error,
            )
        return failure

    def get_dead_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent dead tasks."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_failures WHERE is_dead = 1 ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_failures(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent failures (dead or not)."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_failures ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        """Return failure statistics."""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM task_failures").fetchone()[0]
            dead = conn.execute(
                "SELECT COUNT(*) FROM task_failures WHERE is_dead = 1"
            ).fetchone()[0]
            recent = conn.execute(
                "SELECT COUNT(*) FROM task_failures WHERE timestamp > ?",
                (time.time() - 3600,),
            ).fetchone()[0]
            top_tasks = conn.execute(
                "SELECT task_name, COUNT(*) as cnt FROM task_failures "
                "GROUP BY task_name ORDER BY cnt DESC LIMIT 5"
            ).fetchall()
        return {
            "total_failures": total,
            "dead_tasks": dead,
            "failures_last_hour": recent,
            "top_failing_tasks": [{"name": r[0], "count": r[1]} for r in top_tasks],
        }

    def clear_resolved(self, task_id: str) -> None:
        """Remove failure records for a task that has been resolved."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM task_failures WHERE task_id = ?", (task_id,)
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_failures (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id      TEXT NOT NULL,
                    task_name    TEXT NOT NULL,
                    error_type   TEXT,
                    error_message TEXT,
                    attempt      INTEGER,
                    timestamp    REAL,
                    payload      TEXT,
                    is_dead      INTEGER DEFAULT 0
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_id ON task_failures (task_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_is_dead ON task_failures (is_dead)"
            )
            conn.commit()

    def _insert_failure(self, failure: TaskFailure) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO task_failures
                   (task_id, task_name, error_type, error_message, attempt, timestamp, payload, is_dead)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    failure.task_id, failure.task_name,
                    failure.error_type, failure.error_message,
                    failure.attempt, failure.timestamp,
                    json.dumps(failure.payload) if failure.payload else None,
                    1 if failure.is_dead else 0,
                ),
            )
            conn.commit()

    def _check_alert_threshold(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            dead = conn.execute(
                "SELECT COUNT(*) FROM task_failures WHERE is_dead = 1"
            ).fetchone()[0]
        if dead >= self.alert_threshold:
            logger.critical(
                "FailureHandler: ALERT — %d dead tasks accumulated!", dead
            )
