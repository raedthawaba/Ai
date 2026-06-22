"""Latency Tracker — قياس وتتبّع زمن استجابة البحث."""
from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass
class LatencyRecord:
    """سجل قياس زمن واحد."""
    operation: str
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    metadata: Dict = field(default_factory=dict)


class LatencyTracker:
    """
    يتتبّع زمن الاستجابة لعمليات البحث والـ embedding.
    يحتفظ بـ sliding window من آخر N سجل.
    """

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self._records: Deque[LatencyRecord] = deque(maxlen=window_size)

    def record(
        self,
        operation: str,
        latency_ms: float,
        success: bool = True,
        metadata: Optional[Dict] = None,
    ) -> None:
        self._records.append(LatencyRecord(
            operation=operation,
            latency_ms=latency_ms,
            success=success,
            metadata=metadata or {},
        ))

    def stats(self, operation: Optional[str] = None) -> Dict:
        records = [
            r for r in self._records
            if (operation is None or r.operation == operation) and r.success
        ]
        if not records:
            return {"count": 0, "operation": operation}

        latencies = [r.latency_ms for r in records]
        return {
            "operation": operation or "all",
            "count": len(latencies),
            "mean_ms": round(statistics.mean(latencies), 2),
            "median_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 2),
            "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "success_rate": round(
                sum(1 for r in self._records if r.success) / len(self._records), 3
            ),
        }

    def all_operations(self) -> List[str]:
        return list({r.operation for r in self._records})

    def clear(self) -> None:
        self._records.clear()
