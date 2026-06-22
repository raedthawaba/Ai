"""Tests for Retry & Failure System — section 6.8."""
from __future__ import annotations

import time
import tempfile
from pathlib import Path

import pytest

from workers.retry_manager import RetryConfig, RetryManager, RetryStatus


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == 3
        assert cfg.initial_delay == 1.0
        assert cfg.backoff_factor == 2.0
        assert cfg.jitter is True

    def test_custom(self):
        cfg = RetryConfig(max_attempts=5, initial_delay=2.0)
        assert cfg.max_attempts == 5
        assert cfg.initial_delay == 2.0


class TestRetryManager:
    def test_register(self):
        rm = RetryManager()
        state = rm.register("task-001", "my.task")
        assert state.task_id == "task-001"
        assert state.task_name == "my.task"
        assert state.status == RetryStatus.PENDING

    def test_record_failure_increments_attempts(self):
        rm = RetryManager()
        rm.register("t-001", "task")
        state = rm.record_failure("t-001", "oops")
        assert state.attempts == 1
        assert state.last_error == "oops"

    def test_exhausted_after_max_attempts(self):
        cfg = RetryConfig(max_attempts=3, jitter=False)
        rm = RetryManager(cfg)
        rm.register("t-x", "task")
        for i in range(3):
            state = rm.record_failure("t-x", f"error {i}")
        assert state.is_exhausted
        assert state.status == RetryStatus.DEAD

    def test_should_retry_true_before_exhaustion(self):
        rm = RetryManager()
        rm.register("t-y", "task")
        rm.record_failure("t-y", "err1")
        assert rm.should_retry("t-y") is True

    def test_should_retry_false_when_dead(self):
        cfg = RetryConfig(max_attempts=1, jitter=False)
        rm = RetryManager(cfg)
        rm.register("t-z", "task")
        rm.record_failure("t-z", "fatal")
        assert rm.should_retry("t-z") is False

    def test_compute_delay_exponential(self):
        cfg = RetryConfig(initial_delay=1.0, backoff_factor=2.0, jitter=False)
        rm = RetryManager(cfg)
        assert rm.compute_delay(1) == 1.0
        assert rm.compute_delay(2) == 2.0
        assert rm.compute_delay(3) == 4.0

    def test_compute_delay_respects_max(self):
        cfg = RetryConfig(initial_delay=100.0, max_delay=200.0, backoff_factor=3.0, jitter=False)
        rm = RetryManager(cfg)
        assert rm.compute_delay(5) <= 200.0

    def test_record_success(self):
        rm = RetryManager()
        rm.register("t-s", "task")
        rm.record_failure("t-s", "err")
        rm.record_success("t-s")
        state = rm.get_state("t-s")
        assert state.status == RetryStatus.SUCCESS

    def test_dead_tasks_list(self):
        cfg = RetryConfig(max_attempts=1, jitter=False)
        rm = RetryManager(cfg)
        rm.register("dead-1", "task")
        rm.register("alive-1", "task")
        rm.record_failure("dead-1", "fatal")
        dead = rm.dead_tasks()
        assert len(dead) == 1
        assert dead[0].task_id == "dead-1"

    def test_summary(self):
        rm = RetryManager()
        rm.register("s-1", "task")
        rm.register("s-2", "task")
        rm.record_success("s-1")
        summary = rm.summary()
        assert summary["total"] == 2
        assert summary["success"] == 1

    def test_clear_completed(self):
        rm = RetryManager()
        rm.register("c-1", "task")
        rm.record_success("c-1")
        removed = rm.clear_completed()
        assert removed == 1
        assert rm.get_state("c-1") is None


class TestFailureHandler:
    def test_record_and_retrieve(self, tmp_path):
        from workers.failure_handler import FailureHandler
        handler = FailureHandler(db_path=tmp_path / "failures.db")
        handler.record_failure(
            task_id="f-001",
            task_name="my.task",
            error=ValueError("something broke"),
            attempt=1,
        )
        failures = handler.get_recent_failures()
        assert len(failures) == 1
        assert failures[0]["task_id"] == "f-001"

    def test_dead_after_max_retries(self, tmp_path):
        from workers.failure_handler import FailureHandler
        handler = FailureHandler(db_path=tmp_path / "failures.db", max_retries_before_dead=3)
        handler.record_failure("f-002", "task", ValueError("err"), attempt=3)
        dead = handler.get_dead_tasks()
        assert len(dead) == 1

    def test_stats(self, tmp_path):
        from workers.failure_handler import FailureHandler
        handler = FailureHandler(db_path=tmp_path / "failures.db")
        handler.record_failure("s-001", "task.a", RuntimeError("x"), attempt=1)
        handler.record_failure("s-002", "task.a", RuntimeError("y"), attempt=1)
        stats = handler.stats()
        assert stats["total_failures"] == 2
        assert len(stats["top_failing_tasks"]) >= 1


class TestBackpressure:
    def test_circuit_breaker_starts_closed(self):
        from workers.backpressure import CircuitBreaker
        cb = CircuitBreaker("test")
        assert cb.allows_requests is True
        assert not cb.is_open

    def test_circuit_opens_after_failures(self):
        from workers.backpressure import CircuitBreaker, CircuitBreakerConfig
        cfg = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config=cfg)
        for _ in range(3):
            cb.record_failure()
        assert cb.is_open

    def test_circuit_closes_after_recovery(self):
        from workers.backpressure import CircuitBreaker, CircuitBreakerConfig
        cfg = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.01, success_threshold=1)
        cb = CircuitBreaker("test", config=cfg)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open
        time.sleep(0.02)
        assert cb.allows_requests  # HALF_OPEN
        cb.record_success()
        assert not cb.is_open

    def test_rate_limiter_allows_within_capacity(self):
        from workers.backpressure import RateLimiter
        rl = RateLimiter(rate=10.0, capacity=5.0)
        for _ in range(5):
            assert rl.acquire() is True

    def test_rate_limiter_blocks_when_empty(self):
        from workers.backpressure import RateLimiter
        rl = RateLimiter(rate=0.001, capacity=1.0)
        rl.acquire()  # use the token
        result = rl.acquire(timeout=0.01)
        assert result is False

    def test_backpressure_manager_can_submit(self):
        from workers.backpressure import BackpressureManager
        bpm = BackpressureManager(default_rate=100.0, default_capacity=100.0)
        assert bpm.can_submit("ingestion") is True

    def test_backpressure_manager_status(self):
        from workers.backpressure import BackpressureManager
        bpm = BackpressureManager()
        bpm.get_breaker("processing")
        bpm.get_limiter("processing")
        status = bpm.status()
        assert "breakers" in status
        assert "limiters" in status
