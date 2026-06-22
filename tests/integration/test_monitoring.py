"""اختبارات Phase 6 — Monitoring & Observability."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# StructuredLogger Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestStructuredLogger:
    def test_get_logger_returns_logger(self):
        from shared.logging.structured_logger import get_logger
        logger = get_logger("test")
        assert logger.name == "hajeen.test"

    def test_set_and_get_correlation_id(self):
        from shared.logging.structured_logger import set_correlation_id, get_correlation_id
        set_correlation_id("test-corr-001")
        assert get_correlation_id() == "test-corr-001"

    def test_set_and_get_request_id(self):
        from shared.logging.structured_logger import set_request_id, get_request_id
        set_request_id("req-001")
        assert get_request_id() == "req-001"

    def test_set_and_get_pipeline_id(self):
        from shared.logging.structured_logger import set_pipeline_id, get_pipeline_id
        set_pipeline_id("pipe-001")
        assert get_pipeline_id() == "pipe-001"

    def test_structured_formatter_produces_json(self):
        import logging
        from shared.logging.structured_logger import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=1, msg="test message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "test message"
        assert data["level"] == "INFO"
        assert "timestamp" in data

    def test_structured_formatter_includes_service(self):
        import logging
        from shared.logging.structured_logger import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=1, msg="error msg", args=(), exc_info=None,
        )
        data = json.loads(formatter.format(record))
        assert "service" in data

    def test_configure_logging_creates_log_dir(self):
        from shared.logging.structured_logger import configure_logging
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "test_logs")
            configure_logging(level="DEBUG", log_dir=log_dir, json_console=False)
            assert os.path.isdir(log_dir)

    def test_audit_logger_writes_entries(self):
        from shared.logging.structured_logger import AuditLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = os.path.join(tmpdir, "audit.jsonl")
            logger = AuditLogger(audit_log_path=audit_path)
            logger.log(
                event="user_login",
                actor="user_123",
                resource="/api/login",
                outcome="success",
            )
            assert os.path.exists(audit_path)
            with open(audit_path) as f:
                entry = json.loads(f.readline())
                assert entry["event"] == "user_login"
                assert entry["actor"] == "user_123"

    def test_get_audit_logger_singleton(self):
        from shared.logging.structured_logger import get_audit_logger, _audit
        import shared.logging.structured_logger as sl
        sl._audit = None
        a1 = get_audit_logger()
        a2 = get_audit_logger()
        assert a1 is a2
        sl._audit = None


# ──────────────────────────────────────────────────────────────────────────────
# PrometheusMetrics Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPrometheusMetrics:
    def test_metrics_import_without_crash(self):
        from monitoring.metrics.prometheus_metrics import (
            api_requests_total,
            embedding_requests_total,
            vector_search_total,
            retrieval_requests_total,
            inference_requests_total,
        )
        assert True  # لا استثناء = نجح الاستيراد

    def test_track_latency_context_manager(self):
        from monitoring.metrics.prometheus_metrics import track_latency, retrieval_latency_seconds
        import time
        with track_latency(retrieval_latency_seconds, strategy="semantic"):
            time.sleep(0.001)
        assert True

    def test_get_metrics_text_returns_string(self):
        from monitoring.metrics.prometheus_metrics import get_metrics_text
        text = get_metrics_text()
        assert isinstance(text, str)

    def test_fallback_metric_is_silent(self):
        from monitoring.metrics.prometheus_metrics import _FallbackMetric
        m = _FallbackMetric()
        m.inc()
        m.dec()
        m.set(0)
        m.observe(1.0)
        assert True


# ──────────────────────────────────────────────────────────────────────────────
# HealthChecker Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestHealthChecker:
    @pytest.mark.asyncio
    async def test_check_all_returns_system_health(self):
        from monitoring.health.health_checker import HealthChecker, HealthStatus
        checker = HealthChecker(timeout=5.0)
        health = await checker.check_all()
        assert health.status in list(HealthStatus)
        assert len(health.components) > 0

    @pytest.mark.asyncio
    async def test_check_memory_component(self):
        from monitoring.health.health_checker import HealthChecker, HealthStatus
        checker = HealthChecker()
        result = await checker.check_one("memory")
        assert result.name == "memory"
        assert result.status in list(HealthStatus)

    @pytest.mark.asyncio
    async def test_check_database_component(self):
        from monitoring.health.health_checker import HealthChecker
        checker = HealthChecker()
        result = await checker.check_one("database")
        assert result.name == "database"

    @pytest.mark.asyncio
    async def test_custom_check_registration(self):
        from monitoring.health.health_checker import HealthChecker, ComponentHealth, HealthStatus

        def my_check():
            return ComponentHealth(name="custom", status=HealthStatus.OK, message="all good")

        checker = HealthChecker()
        checker.register("custom", my_check)
        result = await checker.check_one("custom")
        assert result.name == "custom"
        assert result.status == HealthStatus.OK

    @pytest.mark.asyncio
    async def test_unknown_check_returns_unknown(self):
        from monitoring.health.health_checker import HealthChecker, HealthStatus
        checker = HealthChecker()
        result = await checker.check_one("nonexistent_check")
        assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_check_timeout_returns_down(self):
        from monitoring.health.health_checker import HealthChecker, HealthStatus

        async def slow_check():
            await asyncio.sleep(10)

        checker = HealthChecker(timeout=0.01)
        checker.register("slow", slow_check)
        result = await checker.check_one("slow")
        assert result.status == HealthStatus.DOWN
        assert "timeout" in result.message

    @pytest.mark.asyncio
    async def test_startup_check_runs_all(self):
        from monitoring.health.health_checker import HealthChecker
        checker = HealthChecker(timeout=5.0)
        result = await checker.startup_check()
        assert isinstance(result, bool)

    def test_self_test_returns_ready(self):
        from monitoring.health.health_checker import HealthChecker
        checker = HealthChecker()
        result = checker.self_test()
        assert result["status"] == "ready"
        assert "checks_registered" in result

    def test_component_health_to_dict(self):
        from monitoring.health.health_checker import ComponentHealth, HealthStatus
        h = ComponentHealth(name="test", status=HealthStatus.OK, message="ok")
        d = h.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "ok"

    @pytest.mark.asyncio
    async def test_overall_status_is_down_when_one_component_down(self):
        from monitoring.health.health_checker import HealthChecker, ComponentHealth, HealthStatus

        def failing_check():
            raise RuntimeError("component failed")

        checker = HealthChecker(timeout=1.0)
        checker._checks = {"failing": failing_check}
        health = await checker.check_all()
        assert health.status == HealthStatus.DOWN
