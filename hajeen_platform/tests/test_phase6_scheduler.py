"""Tests for APScheduler — section 6.6."""
from __future__ import annotations

import time
import pytest


def _dummy_job():
    """Serialisable placeholder job function."""
    pass


class TestCronScheduler:
    def setup_method(self):
        from data_engine.ingestion.schedulers.cron_scheduler import CronScheduler
        # Use memory job store so no serialisation of lambdas is needed
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor

        self.scheduler = CronScheduler()
        # Override _make_scheduler to use memory job store
        self.scheduler._scheduler = None

    def _start_with_memory_store(self):
        """Start scheduler with in-memory job store (avoids pickle issues in tests)."""
        if self.scheduler._scheduler and self.scheduler._scheduler.running:
            return
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=2)}
        job_defaults = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}

        self.scheduler._scheduler = BackgroundScheduler(
            jobstores=jobstores, executors=executors,
            job_defaults=job_defaults, timezone="UTC",
        )
        self.scheduler._scheduler.add_listener(
            self.scheduler._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )
        self.scheduler._scheduler.start()

    def teardown_method(self):
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass

    def test_start_and_is_running(self):
        self._start_with_memory_store()
        assert self.scheduler.is_running is True

    def test_stop(self):
        self._start_with_memory_store()
        self.scheduler.shutdown()
        assert self.scheduler.is_running is False

    def test_add_interval_job(self):
        self._start_with_memory_store()
        job_id = self.scheduler.add_interval_job(
            func=_dummy_job,
            seconds=3600,
            job_id="test-interval",
            name="Test Interval",
        )
        assert job_id == "test-interval"
        jobs = self.scheduler.list_jobs()
        assert any(j["id"] == "test-interval" for j in jobs)

    def test_add_cron_job(self):
        self._start_with_memory_store()
        job_id = self.scheduler.add_cron_job(
            func=_dummy_job,
            cron_expression="0 */6 * * *",
            job_id="test-cron",
            name="Test Cron",
        )
        assert job_id == "test-cron"
        job = self.scheduler.get_job("test-cron")
        assert job is not None

    def test_invalid_cron_raises(self):
        self._start_with_memory_store()
        with pytest.raises(ValueError, match="Invalid cron"):
            self.scheduler.add_cron_job(_dummy_job, "invalid", "bad-cron")

    def test_add_one_time_job(self):
        from datetime import datetime, timezone, timedelta
        self._start_with_memory_store()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        job_id = self.scheduler.add_one_time_job(
            func=_dummy_job,
            run_at=future,
            job_id="test-onetime",
        )
        assert job_id == "test-onetime"

    def test_pause_and_resume_job(self):
        self._start_with_memory_store()
        self.scheduler.add_interval_job(_dummy_job, seconds=3600, job_id="pausable")
        paused = self.scheduler.pause_job("pausable")
        assert paused is True
        job = self.scheduler.get_job("pausable")
        assert job["paused"] is True
        resumed = self.scheduler.resume_job("pausable")
        assert resumed is True
        job = self.scheduler.get_job("pausable")
        assert job["paused"] is False

    def test_remove_job(self):
        self._start_with_memory_store()
        self.scheduler.add_interval_job(_dummy_job, seconds=3600, job_id="removable")
        removed = self.scheduler.remove_job("removable")
        assert removed is True
        assert self.scheduler.get_job("removable") is None

    def test_remove_nonexistent_job(self):
        self._start_with_memory_store()
        removed = self.scheduler.remove_job("does-not-exist")
        assert removed is False

    def test_list_jobs_empty(self):
        self._start_with_memory_store()
        jobs = self.scheduler.list_jobs()
        assert isinstance(jobs, list)

    def test_multiple_jobs(self):
        self._start_with_memory_store()
        self.scheduler.add_interval_job(_dummy_job, seconds=100, job_id="j1", name="Job 1")
        self.scheduler.add_interval_job(_dummy_job, seconds=200, job_id="j2", name="Job 2")
        jobs = self.scheduler.list_jobs()
        assert len(jobs) == 2

    def test_replace_existing_job(self):
        self._start_with_memory_store()
        self.scheduler.add_interval_job(_dummy_job, seconds=100, job_id="rep-1")
        self.scheduler.add_interval_job(_dummy_job, seconds=200, job_id="rep-1", replace_existing=True)
        jobs = self.scheduler.list_jobs()
        rep_jobs = [j for j in jobs if j["id"] == "rep-1"]
        assert len(rep_jobs) == 1

    def test_get_nonexistent_job(self):
        self._start_with_memory_store()
        assert self.scheduler.get_job("no-such-job") is None
