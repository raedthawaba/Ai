"""Job Tracker — Phase 3 (Section 3.4).

تتبّع تاريخ تنفيذ مهام الـ ingestion:
- SQLite persistence
- Job history (success/failure/duration)
- SLA monitoring (اكتشاف المهام المتأخرة)
- Alerting hooks
- Statistics per job_type
- Failed job analysis
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path("./data/job_history.db")
_DB_LOCK = threading.RLock()


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JobRun:
    """سجل تشغيل مهمة واحدة."""

    run_id: str
    job_id: str
    job_type: str
    status: str                          # success | failed | timeout | cancelled
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_s: float = 0.0
    articles_fetched: int = 0
    articles_processed: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_s": round(self.duration_s, 3),
            "articles_fetched": self.articles_fetched,
            "articles_processed": self.articles_processed,
            "error": self.error,
        }


@dataclass
class JobTypeStats:
    """إحصائيات نوع مهمة."""

    job_type: str
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_articles_fetched: int = 0
    avg_duration_s: float = 0.0
    last_run_at: Optional[datetime] = None
    last_run_status: str = ""
    success_rate: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "job_type": self.job_type,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "total_articles_fetched": self.total_articles_fetched,
            "avg_duration_s": round(self.avg_duration_s, 2),
            "success_rate": round(self.success_rate, 3),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
        }


@dataclass
class SLAViolation:
    """انتهاك SLA."""

    job_id: str
    job_type: str
    expected_max_s: float
    actual_s: float
    detected_at: datetime
    severity: str                        # warning | critical


# ─────────────────────────────────────────────────────────────────────────────
# SQLite setup
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_runs (
            run_id             TEXT PRIMARY KEY,
            job_id             TEXT NOT NULL,
            job_type           TEXT NOT NULL,
            status             TEXT NOT NULL,
            started_at         TEXT NOT NULL,
            completed_at       TEXT,
            duration_s         REAL DEFAULT 0,
            articles_fetched   INTEGER DEFAULT 0,
            articles_processed INTEGER DEFAULT 0,
            error              TEXT,
            metadata_json      TEXT,
            created_at         TEXT DEFAULT (datetime('now','utc'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs (job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_job_type ON job_runs (job_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_status ON job_runs (status)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sla_violations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          TEXT,
            job_type        TEXT,
            expected_max_s  REAL,
            actual_s        REAL,
            severity        TEXT,
            detected_at     TEXT DEFAULT (datetime('now','utc'))
        )
    """)
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# JobTracker
# ─────────────────────────────────────────────────────────────────────────────

class JobTracker:
    """تتبّع تاريخ تنفيذ مهام الـ ingestion مع SLA monitoring.

    Parameters
    ----------
    sla_limits:
        قاموس job_type → max_duration_s للـ SLA monitoring.
    alert_hook:
        Callback اختياري يُستدعى عند انتهاك SLA.
    """

    def __init__(
        self,
        sla_limits: Optional[Dict[str, float]] = None,
        alert_hook: Optional[Callable[[SLAViolation], None]] = None,
    ) -> None:
        self.sla_limits = sla_limits or {
            "rss": 60.0,
            "api": 120.0,
            "crawl": 300.0,
            "stream": 3600.0,
        }
        self.alert_hook = alert_hook
        self._in_progress: Dict[str, JobRun] = {}
        self._lock = threading.RLock()

    # ─── Public API ─────────────────────────────────────────────────────

    def start_run(
        self,
        job_id: str,
        job_type: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """تسجيل بداية تشغيل مهمة.

        Returns
        -------
        run_id — معرّف التشغيل الفريد.
        """
        import uuid
        run_id = str(uuid.uuid4())[:12]
        run = JobRun(
            run_id=run_id,
            job_id=job_id,
            job_type=job_type,
            status="running",
            started_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        with self._lock:
            self._in_progress[run_id] = run

        self._persist_run(run)
        logger.info("JobTracker: run started job_id=%s run_id=%s type=%s", job_id, run_id, job_type)
        return run_id

    def complete_run(
        self,
        run_id: str,
        articles_fetched: int = 0,
        articles_processed: int = 0,
        metadata: Optional[Dict] = None,
    ) -> Optional[JobRun]:
        """تسجيل نجاح تشغيل مهمة.

        Returns
        -------
        JobRun المكتمل.
        """
        with self._lock:
            run = self._in_progress.pop(run_id, None)
        if not run:
            logger.warning("JobTracker: run_id=%s not found", run_id)
            return None

        now = datetime.now(timezone.utc)
        run.status = "success"
        run.completed_at = now
        run.duration_s = (now - run.started_at).total_seconds()
        run.articles_fetched = articles_fetched
        run.articles_processed = articles_processed
        if metadata:
            run.metadata.update(metadata)

        self._persist_run(run)
        self._check_sla(run)

        logger.info(
            "JobTracker: run completed run_id=%s duration=%.2fs fetched=%d",
            run_id, run.duration_s, articles_fetched,
        )
        return run

    def fail_run(
        self,
        run_id: str,
        error: str,
        articles_fetched: int = 0,
    ) -> Optional[JobRun]:
        """تسجيل فشل تشغيل مهمة.

        Returns
        -------
        JobRun الفاشل.
        """
        with self._lock:
            run = self._in_progress.pop(run_id, None)
        if not run:
            logger.warning("JobTracker: run_id=%s not found for fail", run_id)
            return None

        now = datetime.now(timezone.utc)
        run.status = "failed"
        run.completed_at = now
        run.duration_s = (now - run.started_at).total_seconds()
        run.error = error[:1000] if error else ""
        run.articles_fetched = articles_fetched

        self._persist_run(run)
        self._check_sla(run)

        logger.error(
            "JobTracker: run failed run_id=%s duration=%.2fs error=%s",
            run_id, run.duration_s, error[:100],
        )
        return run

    # ─── Queries ─────────────────────────────────────────────────────────

    def get_job_history(
        self,
        job_id: str,
        limit: int = 50,
    ) -> List[JobRun]:
        """استرجاع تاريخ تشغيل مهمة."""
        with _DB_LOCK:
            try:
                conn = _ensure_db()
                rows = conn.execute(
                    "SELECT run_id, job_id, job_type, status, started_at, "
                    "completed_at, duration_s, articles_fetched, articles_processed, error "
                    "FROM job_runs WHERE job_id=? ORDER BY started_at DESC LIMIT ?",
                    (job_id, limit),
                ).fetchall()
                conn.close()
                return [self._row_to_run(r) for r in rows]
            except Exception as exc:
                logger.error("JobTracker.get_job_history: error — %s", exc)
                return []

    def get_recent_failures(self, limit: int = 20) -> List[JobRun]:
        """استرجاع أحدث المهام الفاشلة."""
        with _DB_LOCK:
            try:
                conn = _ensure_db()
                rows = conn.execute(
                    "SELECT run_id, job_id, job_type, status, started_at, "
                    "completed_at, duration_s, articles_fetched, articles_processed, error "
                    "FROM job_runs WHERE status='failed' ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                conn.close()
                return [self._row_to_run(r) for r in rows]
            except Exception as exc:
                logger.error("JobTracker.get_recent_failures: error — %s", exc)
                return []

    def get_stats_by_type(self) -> List[JobTypeStats]:
        """إحصائيات مجمّعة لكل نوع مهمة."""
        with _DB_LOCK:
            try:
                conn = _ensure_db()
                rows = conn.execute("""
                    SELECT
                        job_type,
                        COUNT(*) as total,
                        SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                        SUM(articles_fetched) as fetched,
                        AVG(duration_s) as avg_dur,
                        MAX(started_at) as last_run,
                        (SELECT status FROM job_runs j2
                         WHERE j2.job_type=j.job_type
                         ORDER BY started_at DESC LIMIT 1) as last_status
                    FROM job_runs j
                    GROUP BY job_type
                """).fetchall()
                conn.close()

                stats = []
                for row in rows:
                    total = row[1] or 0
                    success = row[2] or 0
                    stats.append(JobTypeStats(
                        job_type=row[0],
                        total_runs=total,
                        successful_runs=success,
                        failed_runs=row[3] or 0,
                        total_articles_fetched=row[4] or 0,
                        avg_duration_s=float(row[5] or 0),
                        last_run_at=datetime.fromisoformat(row[6]) if row[6] else None,
                        last_run_status=row[7] or "",
                        success_rate=success / total if total else 0.0,
                    ))
                return stats
            except Exception as exc:
                logger.error("JobTracker.get_stats_by_type: error — %s", exc)
                return []

    def get_sla_violations(self, limit: int = 50) -> List[Dict]:
        """استرجاع انتهاكات SLA."""
        with _DB_LOCK:
            try:
                conn = _ensure_db()
                rows = conn.execute(
                    "SELECT job_id, job_type, expected_max_s, actual_s, severity, detected_at "
                    "FROM sla_violations ORDER BY detected_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                conn.close()
                return [
                    {
                        "job_id": r[0], "job_type": r[1],
                        "expected_max_s": r[2], "actual_s": r[3],
                        "severity": r[4], "detected_at": r[5],
                    }
                    for r in rows
                ]
            except Exception as exc:
                logger.error("JobTracker.get_sla_violations: error — %s", exc)
                return []

    def get_in_progress(self) -> List[JobRun]:
        """المهام قيد التشغيل حالياً."""
        with self._lock:
            return list(self._in_progress.values())

    # ─── Internal ────────────────────────────────────────────────────────

    def _persist_run(self, run: JobRun) -> None:
        with _DB_LOCK:
            try:
                conn = _ensure_db()
                conn.execute("""
                    INSERT OR REPLACE INTO job_runs
                    (run_id, job_id, job_type, status, started_at, completed_at,
                     duration_s, articles_fetched, articles_processed, error, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run.run_id, run.job_id, run.job_type, run.status,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.duration_s, run.articles_fetched, run.articles_processed,
                    run.error,
                    json.dumps(run.metadata, ensure_ascii=False, default=str),
                ))
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning("JobTracker._persist_run: error — %s", exc)

    def _check_sla(self, run: JobRun) -> None:
        """التحقق من SLA وتسجيل الانتهاكات."""
        max_s = self.sla_limits.get(run.job_type)
        if max_s is None or run.duration_s <= max_s:
            return

        ratio = run.duration_s / max_s
        severity = "critical" if ratio >= 2.0 else "warning"

        violation = SLAViolation(
            job_id=run.job_id,
            job_type=run.job_type,
            expected_max_s=max_s,
            actual_s=run.duration_s,
            detected_at=datetime.now(timezone.utc),
            severity=severity,
        )

        logger.warning(
            "JobTracker: SLA violation job_id=%s type=%s expected=%.0fs actual=%.0fs severity=%s",
            run.job_id, run.job_type, max_s, run.duration_s, severity,
        )

        with _DB_LOCK:
            try:
                conn = _ensure_db()
                conn.execute(
                    "INSERT INTO sla_violations (job_id, job_type, expected_max_s, actual_s, severity) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (violation.job_id, violation.job_type,
                     violation.expected_max_s, violation.actual_s, violation.severity),
                )
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning("JobTracker._check_sla: persist error — %s", exc)

        if self.alert_hook:
            try:
                self.alert_hook(violation)
            except Exception as exc:
                logger.error("JobTracker: alert_hook error — %s", exc)

    @staticmethod
    def _row_to_run(row: tuple) -> JobRun:
        return JobRun(
            run_id=row[0],
            job_id=row[1],
            job_type=row[2],
            status=row[3],
            started_at=datetime.fromisoformat(row[4]) if row[4] else datetime.now(timezone.utc),
            completed_at=datetime.fromisoformat(row[5]) if row[5] else None,
            duration_s=float(row[6] or 0),
            articles_fetched=int(row[7] or 0),
            articles_processed=int(row[8] or 0),
            error=row[9],
        )
