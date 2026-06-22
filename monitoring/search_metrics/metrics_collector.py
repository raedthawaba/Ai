"""Metrics Collector — يجمع إحصائيات البحث في الوقت الفعلي."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Optional

from monitoring.search_metrics.latency_tracker import LatencyTracker
from monitoring.search_metrics.retrieval_evaluator import RetrievalEvaluator


class SearchMetricsCollector:
    """
    يجمع جميع مقاييس البحث الدلالي:
    - latency (embedding + search + retrieval + RAG)
    - retrieval quality (precision, recall, NDCG)
    - throughput
    - error rates
    """

    def __init__(self):
        self._latency = LatencyTracker(window_size=2000)
        self._evaluator = RetrievalEvaluator()
        self._counters: Dict[str, int] = defaultdict(int)
        self._errors: Dict[str, int] = defaultdict(int)
        self._start_time = time.time()

    def record_search(
        self,
        query: str,
        latency_ms: float,
        num_results: int,
        search_type: str = "semantic",
        success: bool = True,
    ) -> None:
        self._latency.record(
            operation=f"search.{search_type}",
            latency_ms=latency_ms,
            success=success,
            metadata={"num_results": num_results},
        )
        self._counters[f"search.{search_type}"] += 1
        if not success:
            self._errors[f"search.{search_type}"] += 1

    def record_embedding(
        self,
        num_texts: int,
        latency_ms: float,
        model_name: str = "",
        success: bool = True,
    ) -> None:
        self._latency.record(
            operation="embedding",
            latency_ms=latency_ms,
            success=success,
            metadata={"num_texts": num_texts, "model": model_name},
        )
        self._counters["embedding"] += num_texts
        if not success:
            self._errors["embedding"] += 1

    def record_rag(
        self,
        latency_ms: float,
        num_citations: int,
        success: bool = True,
    ) -> None:
        self._latency.record("rag", latency_ms, success, {"num_citations": num_citations})
        self._counters["rag"] += 1
        if not success:
            self._errors["rag"] += 1

    def summary(self) -> Dict:
        uptime = time.time() - self._start_time
        all_ops = self._latency.all_operations()
        stats_per_op = {op: self._latency.stats(op) for op in all_ops}
        return {
            "uptime_seconds": round(uptime, 1),
            "counters": dict(self._counters),
            "errors": dict(self._errors),
            "latency_per_operation": stats_per_op,
            "overall": self._latency.stats(),
        }

    def reset(self) -> None:
        self._latency.clear()
        self._counters.clear()
        self._errors.clear()
        self._start_time = time.time()


# Singleton
_COLLECTOR: Optional[SearchMetricsCollector] = None


def get_metrics_collector() -> SearchMetricsCollector:
    global _COLLECTOR
    if _COLLECTOR is None:
        _COLLECTOR = SearchMetricsCollector()
    return _COLLECTOR
