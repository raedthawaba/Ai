"""Tests for Task Monitor & Job Store — sections 6.9, 6.10."""
from __future__ import annotations

import time
import pytest
from pathlib import Path


class TestTaskMonitor:
    def setup_method(self, tmp_path=None):
        from monitoring.task_monitor import TaskMonitor
        import tempfile, os
        self.tmpdir = tempfile.mkdtemp()
        self.monitor = TaskMonitor(db_path=Path(self.tmpdir) / "test_monitor.db")

    def test_on_task_start_creates_record(self):
        rec = self.monitor.on_task_start("task-001", "my.task", queue="ingestion")
        from monitoring.task_monitor import TaskStatus
        assert rec.task_id == "task-001"
        assert rec.task_name == "my.task"
        assert rec.queue == "ingestion"
        assert rec.status == TaskStatus.RUNNING

    def test_on_task_success(self):
        self.monitor.on_task_start("task-002", "my.task")
        self.monitor.on_task_success("task-002", result_summary="Done")
        record = self.monitor.get_task("task-002")
        assert record["status"] == "success"
        assert record["result_summary"] == "Done"

    def test_on_task_failure(self):
        self.monitor.on_task_start("task-003", "my.task")
        self.monitor.on_task_failure("task-003", error="Connection failed")
        record = self.monitor.get_task("task-003")
        assert record["status"] == "failed"
        assert "Connection" in record["last_error"]

    def test_on_task_dead(self):
        from monitoring.task_monitor import TaskStatus
        self.monitor.on_task_start("task-004", "my.task")
        self.monitor.on_task_failure("task-004", error="Fatal", is_dead=True)
        record = self.monitor.get_task("task-004")
        assert record["status"] == TaskStatus.DEAD.value

    def test_on_task_retry(self):
        from monitoring.task_monitor import TaskStatus
        self.monitor.on_task_start("task-005", "my.task")
        self.monitor.on_task_retry("task-005", error="Timeout")
        record = self.monitor.get_task("task-005")
        assert record["status"] == TaskStatus.RETRYING.value

    def test_running_tasks(self):
        self.monitor.on_task_start("r-001", "my.task")
        self.monitor.on_task_start("r-002", "my.task")
        running = self.monitor.running_tasks()
        ids = [t["task_id"] for t in running]
        assert "r-001" in ids
        assert "r-002" in ids

    def test_failed_tasks(self):
        self.monitor.on_task_start("f-001", "fail.task")
        self.monitor.on_task_failure("f-001", error="Broke")
        failed = self.monitor.failed_tasks()
        assert any(t["task_id"] == "f-001" for t in failed)

    def test_retrying_tasks(self):
        self.monitor.on_task_start("ret-001", "my.task")
        self.monitor.on_task_retry("ret-001", error="Retry me")
        retrying = self.monitor.retrying_tasks()
        assert any(t["task_id"] == "ret-001" for t in retrying)

    def test_summary_counts(self):
        self.monitor.on_task_start("s-001", "task.a")
        self.monitor.on_task_success("s-001")
        self.monitor.on_task_start("s-002", "task.b")
        self.monitor.on_task_failure("s-002", error="err")
        summary = self.monitor.summary()
        assert summary["total_tasks"] >= 2
        assert "by_status" in summary

    def test_get_task_not_found(self):
        assert self.monitor.get_task("nonexistent") is None

    def test_task_duration_ms(self):
        from monitoring.task_monitor import TaskRecord, TaskStatus
        rec = TaskRecord(
            task_id="dur-001", task_name="t",
            started_at=1000.0, finished_at=1002.0,
            status=TaskStatus.SUCCESS,
        )
        assert rec.duration_ms == 2000.0


class TestJobStore:
    def setup_method(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        from data_engine.storage.metadata_store.job_store import JobStore
        self.store = JobStore(db_path=Path(self.tmpdir) / "test_jobs.db")

    def test_save_and_get_job(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        job = ScheduledJob(
            job_id="job-001",
            name="Test Job",
            channel_id="ch-123",
            trigger_type="cron",
            trigger_value="0 */6 * * *",
        )
        self.store.save_job(job)
        retrieved = self.store.get_job("job-001")
        assert retrieved is not None
        assert retrieved.job_id == "job-001"
        assert retrieved.channel_id == "ch-123"

    def test_list_jobs(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        for i in range(3):
            self.store.save_job(ScheduledJob(
                job_id=f"lj-{i}", name=f"Job {i}",
                channel_id=None, trigger_type="interval",
                trigger_value="60",
            ))
        jobs = self.store.list_jobs()
        assert len(jobs) == 3

    def test_list_enabled_only(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        self.store.save_job(ScheduledJob("en-1", "A", None, "cron", "* * * * *", enabled=True))
        self.store.save_job(ScheduledJob("en-2", "B", None, "cron", "* * * * *", enabled=False))
        enabled = self.store.list_jobs(enabled_only=True)
        assert all(j.enabled for j in enabled)

    def test_update_job_status(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        self.store.save_job(ScheduledJob("upd-1", "X", None, "cron", "* * * * *"))
        updated = self.store.update_job_status("upd-1", enabled=False)
        assert updated is True
        job = self.store.get_job("upd-1")
        assert job.enabled is False

    def test_record_job_run(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        self.store.save_job(ScheduledJob("run-1", "R", None, "cron", "* * * * *"))
        self.store.record_job_run("run-1")
        job = self.store.get_job("run-1")
        assert job.last_run_at is not None
        assert job.run_count == 1

    def test_delete_job(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        self.store.save_job(ScheduledJob("del-1", "D", None, "cron", "* * * * *"))
        deleted = self.store.delete_job("del-1")
        assert deleted is True
        assert self.store.get_job("del-1") is None

    def test_delete_nonexistent(self):
        assert self.store.delete_job("no-such-job") is False

    def test_record_task(self):
        self.store.record_task("t-001", "my.task", "success", duration_ms=123.4)
        history = self.store.get_task_history(limit=10)
        assert any(h["task_id"] == "t-001" for h in history)

    def test_stats(self):
        from data_engine.storage.metadata_store.job_store import ScheduledJob
        self.store.save_job(ScheduledJob("st-1", "S", None, "cron", "* * * * *"))
        self.store.record_task("st-t1", "task", "success")
        stats = self.store.stats()
        assert stats["scheduled_jobs"] == 1
        assert stats["total_tasks"] >= 1
