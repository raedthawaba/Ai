"""Prometheus Metrics — Phase 6 — مقاييس شاملة للمنصة."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

# Lazy imports — لا يُطلب prometheus_client إذا لم يكن متاحاً
try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary,
        CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST,
        start_http_server,
    )
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    logger.warning("prometheus_client غير مثبّت — metrics disabled")


class _FallbackMetric:
    """بديل صامت عند غياب prometheus_client."""
    def __init__(self, *args: Any, **kwargs: Any) -> None: pass
    def inc(self, *a: Any, **k: Any) -> None: pass
    def dec(self, *a: Any, **k: Any) -> None: pass
    def set(self, *a: Any, **k: Any) -> None: pass
    def observe(self, *a: Any, **k: Any) -> None: pass
    def labels(self, *a: Any, **k: Any) -> "_FallbackMetric": return self
    def time(self) -> Any:
        from contextlib import contextmanager
        @contextmanager
        def _ctx():
            yield
        return _ctx()


def _counter(name: str, description: str, labels: list = None) -> Any:
    if not _PROM_AVAILABLE:
        return _FallbackMetric()
    kwargs = {"labelnames": labels or []}
    return Counter(name, description, **kwargs)


def _gauge(name: str, description: str, labels: list = None) -> Any:
    if not _PROM_AVAILABLE:
        return _FallbackMetric()
    kwargs = {"labelnames": labels or []}
    return Gauge(name, description, **kwargs)


def _histogram(name: str, description: str, labels: list = None, buckets: list = None) -> Any:
    if not _PROM_AVAILABLE:
        return _FallbackMetric()
    kwargs = {"labelnames": labels or []}
    if buckets:
        kwargs["buckets"] = buckets
    return Histogram(name, description, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# API Metrics
# ──────────────────────────────────────────────────────────────────────────────
api_requests_total = _counter(
    "hajeen_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)
api_request_duration_seconds = _histogram(
    "hajeen_api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
api_errors_total = _counter(
    "hajeen_api_errors_total",
    "Total API errors",
    ["endpoint", "error_type"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Ingestion Metrics
# ──────────────────────────────────────────────────────────────────────────────
ingestion_articles_total = _counter(
    "hajeen_ingestion_articles_total",
    "Total articles ingested",
    ["channel", "source_type"],
)
ingestion_errors_total = _counter(
    "hajeen_ingestion_errors_total",
    "Ingestion errors",
    ["channel", "error_type"],
)
ingestion_duration_seconds = _histogram(
    "hajeen_ingestion_duration_seconds",
    "Ingestion pipeline duration",
    ["channel"],
)
ingestion_queue_size = _gauge(
    "hajeen_ingestion_queue_size",
    "Current ingestion queue size",
    ["queue_name"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Embedding Metrics
# ──────────────────────────────────────────────────────────────────────────────
embedding_requests_total = _counter(
    "hajeen_embedding_requests_total",
    "Total embedding requests",
    ["model"],
)
embedding_latency_seconds = _histogram(
    "hajeen_embedding_latency_seconds",
    "Embedding generation latency",
    ["model"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)
embedding_cache_hits_total = _counter(
    "hajeen_embedding_cache_hits_total",
    "Embedding cache hits",
)
embedding_cache_misses_total = _counter(
    "hajeen_embedding_cache_misses_total",
    "Embedding cache misses",
)

# ──────────────────────────────────────────────────────────────────────────────
# Vector Metrics
# ──────────────────────────────────────────────────────────────────────────────
vector_index_size = _gauge(
    "hajeen_vector_index_size",
    "Number of vectors in index",
    ["backend", "collection"],
)
vector_search_latency_seconds = _histogram(
    "hajeen_vector_search_latency_seconds",
    "Vector search latency",
    ["backend"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)
vector_search_total = _counter(
    "hajeen_vector_search_total",
    "Total vector search requests",
    ["backend"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Retrieval Metrics
# ──────────────────────────────────────────────────────────────────────────────
retrieval_requests_total = _counter(
    "hajeen_retrieval_requests_total",
    "Total retrieval requests",
    ["strategy"],
)
retrieval_latency_seconds = _histogram(
    "hajeen_retrieval_latency_seconds",
    "Retrieval latency",
    ["strategy"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)
retrieval_hits_count = _histogram(
    "hajeen_retrieval_hits_count",
    "Number of results returned per retrieval",
    buckets=[0, 1, 2, 3, 5, 10, 20],
)

# ──────────────────────────────────────────────────────────────────────────────
# Inference Metrics
# ──────────────────────────────────────────────────────────────────────────────
inference_requests_total = _counter(
    "hajeen_inference_requests_total",
    "Total inference requests",
    ["model", "stream"],
)
inference_latency_seconds = _histogram(
    "hajeen_inference_latency_seconds",
    "Inference latency",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
inference_tokens_total = _counter(
    "hajeen_inference_tokens_total",
    "Total tokens generated",
    ["model"],
)
inference_errors_total = _counter(
    "hajeen_inference_errors_total",
    "Inference errors",
    ["model", "error_type"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Self-Reflection Metrics
# ──────────────────────────────────────────────────────────────────────────────
hajeen_reflection_reports_total = _counter(
    "hajeen_reflection_reports_total",
    "Total self-reflection reports generated",
    ["status", "goal_id"],
)
hajeen_reflection_score_overall = _gauge(
    "hajeen_reflection_score_overall",
    "Overall reflection score",
    ["goal_id"],
)
hajeen_reflection_latency_seconds = _histogram(
    "hajeen_reflection_latency_seconds",
    "Self-reflection process latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ──────────────────────────────────────────────────────────────────────────────
# Self-Evolution Metrics
# ──────────────────────────────────────────────────────────────────────────────
hajeen_evolution_proposals_total = _counter(
    "hajeen_evolution_proposals_total",
    "Total self-evolution proposals generated",
    ["type", "status"],
)
hajeen_evolution_implementation_total = _counter(
    "hajeen_evolution_implementation_total",
    "Total self-evolution proposals implemented",
    ["type", "status"],
)
hajeen_evolution_evaluation_latency_seconds = _histogram(
    "hajeen_evolution_evaluation_latency_seconds",
    "Self-evolution proposal evaluation latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# ──────────────────────────────────────────────────────────────────────────────
# Memory & Worker Metrics
# ──────────────────────────────────────────────────────────────────────────────
worker_active_count = _gauge(
    "hajeen_worker_active_count",
    "Active worker count",
    ["worker_type"],
)
memory_usage_bytes = _gauge(
    "hajeen_memory_usage_bytes",
    "Process memory usage in bytes",
)
scheduler_jobs_total = _counter(
    "hajeen_scheduler_jobs_total",
    "Scheduler jobs executed",
    ["job_type", "status"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

@contextmanager
def track_latency(metric: Any, **labels: str) -> Generator:
    """Context manager لقياس الزمن وتسجيله في histogram."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        try:
            if labels:
                metric.labels(**labels).observe(elapsed)
            else:
                metric.observe(elapsed)
        except Exception:
            pass


def update_memory_metrics() -> None:
    try:
        import psutil
        proc = psutil.Process()
        memory_usage_bytes.set(proc.memory_info().rss)
    except Exception:
        pass


def start_metrics_server(port: int = 9090) -> None:
    if not _PROM_AVAILABLE:
        logger.warning("Prometheus metrics server لا يمكن تشغيله — prometheus_client غير مثبّت")
        return
    start_http_server(port)
    logger.info("Prometheus metrics server بدأ على port %d", port)


def get_metrics_text() -> str:
    if not _PROM_AVAILABLE:
        return "# prometheus_client not available\n"
    return generate_latest().decode("utf-8")
