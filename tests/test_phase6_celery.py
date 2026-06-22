"""Tests for Celery Tasks (eager mode) — sections 6.3, 6.4, 6.5."""
from __future__ import annotations

import os
import pytest
from datetime import datetime, timezone

# Force in-memory Celery for tests
os.environ.setdefault("CELERY_USE_MEMORY", "1")


@pytest.fixture(autouse=True)
def celery_eager():
    """Run Celery tasks synchronously in tests."""
    from workers.celery_app import app
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield
    app.conf.task_always_eager = False


def _make_valid_article(idx: int) -> dict:
    """Create a fully valid Article dict matching the schema."""
    return {
        "id": f"art-{idx}",
        "title": f"Test Article {idx} — Valid Title",
        "content": f"This is valid test article content number {idx}. " * 6,
        "url": f"https://example.com/article-{idx}",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source_id": "ch-test",
            "language": "en",
            "tags": [],
            "entities": [],
            "extra": {},
        },
    }


class TestHealthCheckTask:
    def test_health_check_returns_ok(self):
        from workers.tasks.ingestion_tasks import health_check_task
        result = health_check_task.delay()
        res = result.get(timeout=5)
        assert res["status"] == "ok"
        assert "timestamp" in res
        assert "registered_channels" in res


class TestValidateSourcesTask:
    def test_validate_with_no_channels(self):
        from workers.tasks.ingestion_tasks import validate_sources_task
        from data_engine.channels.registry import ChannelRegistry
        ChannelRegistry.clear()

        result = validate_sources_task.delay()
        res = result.get(timeout=10)
        assert "results" in res
        assert "total" in res

    def test_validate_with_channel_ids_filter(self):
        from workers.tasks.ingestion_tasks import validate_sources_task
        from data_engine.channels.registry import ChannelRegistry
        ChannelRegistry.clear()

        result = validate_sources_task.delay(channel_ids=["nonexistent-id"])
        res = result.get(timeout=10)
        assert res["total"] == 0


class TestProcessArticleBatch:
    def test_process_empty_batch(self):
        from workers.tasks.processing_tasks import process_article_batch
        result = process_article_batch.delay(articles_raw=[], source_id="test")
        res = result.get(timeout=10)
        assert res["input_count"] == 0
        assert res["output_count"] == 0

    def test_process_batch_returns_metrics(self):
        from workers.tasks.processing_tasks import process_article_batch
        articles = [_make_valid_article(i) for i in range(2)]
        result = process_article_batch.delay(articles_raw=articles, source_id="test")
        res = result.get(timeout=30)
        assert "input_count" in res
        assert "output_count" in res
        assert "rejection_rate" in res
        assert "errors" in res

    def test_process_batch_has_task_id(self):
        from workers.tasks.processing_tasks import process_article_batch
        articles = [_make_valid_article(0)]
        result = process_article_batch.delay(articles_raw=articles, source_id="test2")
        res = result.get(timeout=30)
        assert "task_id" in res


class TestExecutePipeline:
    def test_execute_pipeline_no_articles(self):
        from workers.tasks.pipeline_tasks import execute_pipeline
        result = execute_pipeline.delay(
            articles_raw=None,
            source_id="test",
            pipeline_name="test_pipeline",
        )
        res = result.get(timeout=30)
        assert "status" in res

    def test_execute_pipeline_with_articles(self):
        from workers.tasks.pipeline_tasks import execute_pipeline
        articles = [_make_valid_article(i) for i in range(2)]
        result = execute_pipeline.delay(
            articles_raw=articles,
            source_id="test",
            pipeline_name="test_pipeline",
        )
        res = result.get(timeout=30)
        assert res["status"] == "success"
        assert "pipeline_name" in res
        assert "elapsed_ms" in res
        assert isinstance(res["stage_traces"], list)

    def test_execute_pipeline_returns_stage_traces(self):
        from workers.tasks.pipeline_tasks import execute_pipeline
        articles = [_make_valid_article(0)]
        result = execute_pipeline.delay(
            articles_raw=articles,
            source_id="trace-test",
            pipeline_name="trace_pipeline",
        )
        res = result.get(timeout=30)
        assert "stage_traces" in res
        for trace in res["stage_traces"]:
            assert "stage" in trace
            assert "in" in trace
            assert "out" in trace
            assert "ms" in trace

    def test_cancel_pipeline(self):
        from workers.tasks.pipeline_tasks import cancel_pipeline
        result = cancel_pipeline.delay("fake-task-id-999")
        res = result.get(timeout=5)
        assert res["status"] == "cancel_requested"
        assert res["task_id"] == "fake-task-id-999"

    def test_execute_pipeline_source_id_in_result(self):
        from workers.tasks.pipeline_tasks import execute_pipeline
        articles = [_make_valid_article(0)]
        result = execute_pipeline.delay(
            articles_raw=articles,
            source_id="mysource",
            pipeline_name="mysource_pipeline",
        )
        res = result.get(timeout=30)
        assert res["source_id"] == "mysource"


class TestCeleryConfig:
    def test_queue_names_defined(self):
        from workers.celery_config import TASK_QUEUES
        assert "default" in TASK_QUEUES
        assert "ingestion" in TASK_QUEUES
        assert "processing" in TASK_QUEUES
        assert "pipeline" in TASK_QUEUES

    def test_task_routes_defined(self):
        from workers.celery_config import TASK_ROUTES
        assert len(TASK_ROUTES) > 0

    def test_beat_schedule_has_health_check(self):
        from workers.celery_config import BEAT_SCHEDULE
        assert "health-check-every-minute" in BEAT_SCHEDULE

    def test_in_memory_mode_env(self):
        assert os.getenv("CELERY_USE_MEMORY") == "1"

    def test_worker_config_defaults(self):
        from workers.celery_config import WORKER_PREFETCH_MULTIPLIER, WORKER_MAX_TASKS_PER_CHILD
        assert WORKER_PREFETCH_MULTIPLIER >= 1
        assert WORKER_MAX_TASKS_PER_CHILD >= 100
