"""Phase 8.9 — Latency Tracker: تتبع زمن الاستجابة."""
from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Dict, List, Optional


@dataclass
class LatencyPoint:
    """قياس زمن استجابة واحد."""
    timestamp: float
    latency_ms: float
    operation: str  # "inference" | "rag" | "embedding" | "stream"
    model: str = ""
    provider: str = ""
    success: bool = True
    queue_wait_ms: float = 0.0


class LatencyTracker:
    """
    تتبع وتحليل زمن الاستجابة.

    يقيس:
    - زمن الـ inference
    - زمن انتظار الطابور
    - زمن الـ RAG retrieval
    - Percentiles: P50, P90, P95, P99
    """

    def __init__(self, window_size: int = 500):
        self._data: Deque[LatencyPoint] = deque(maxlen=window_size)
        self._lock = Lock()
        self._by_operation: Dict[str, List[float]] = {}
        self._error_count = 0
        self._total_count = 0

    def record(
        self,
        latency_ms: float,
        operation: str = "inference",
        model: str = "",
        provider: str = "",
        success: bool = True,
        queue_wait_ms: float = 0.0,
    ) -> LatencyPoint:
        point = LatencyPoint(
            timestamp=time.time(),
            latency_ms=latency_ms,
            operation=operation,
            model=model,
            provider=provider,
            success=success,
            queue_wait_ms=queue_wait_ms,
        )
        with self._lock:
            self._data.append(point)
            if operation not in self._by_operation:
                self._by_operation[operation] = []
            self._by_operation[operation].append(latency_ms)
            if len(self._by_operation[operation]) > 500:
                self._by_operation[operation] = self._by_operation[operation][-500:]
            self._total_count += 1
            if not success:
                self._error_count += 1
        return point

    def _percentile(self, data: List[float], p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = max(0, min(len(sorted_data) - 1, int(len(sorted_data) * p / 100)))
        return round(sorted_data[idx], 2)

    def get_stats(
        self,
        operation: Optional[str] = None,
        minutes: int = 60,
    ) -> Dict:
        cutoff = time.time() - (minutes * 60)

        with self._lock:
            if operation:
                data = [
                    d.latency_ms for d in self._data
                    if d.operation == operation and d.timestamp >= cutoff and d.success
                ]
            else:
                data = [
                    d.latency_ms for d in self._data
                    if d.timestamp >= cutoff and d.success
                ]

        if not data:
            return {
                "count": 0,
                "avg_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
                "p50_ms": 0.0,
                "p90_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "error_rate": 0.0,
            }

        error_rate = (
            self._error_count / max(1, self._total_count)
        ) * 100

        return {
            "count": len(data),
            "avg_ms": round(statistics.mean(data), 2),
            "min_ms": round(min(data), 2),
            "max_ms": round(max(data), 2),
            "p50_ms": self._percentile(data, 50),
            "p90_ms": self._percentile(data, 90),
            "p95_ms": self._percentile(data, 95),
            "p99_ms": self._percentile(data, 99),
            "error_rate_pct": round(error_rate, 2),
        }

    def get_by_operation(self) -> Dict[str, Dict]:
        result = {}
        for op in self._by_operation:
            result[op] = self.get_stats(operation=op)
        return result
