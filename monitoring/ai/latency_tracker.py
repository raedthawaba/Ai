from __future__ import annotations

import math
import time
from collections import deque
from typing import Deque, Dict, List, Optional


class LatencyTracker:
    """Track and compute latency percentiles for AI operations."""

    def __init__(self, window_size: int = 500) -> None:
        self._samples: Deque[float] = deque(maxlen=window_size)
        self._by_operation: Dict[str, Deque[float]] = {}

    def record(self, latency_ms: float, operation: Optional[str] = None) -> None:
        self._samples.append(latency_ms)
        if operation:
            if operation not in self._by_operation:
                self._by_operation[operation] = deque(maxlen=500)
            self._by_operation[operation].append(latency_ms)

    def percentile(self, p: float, samples: Optional[List[float]] = None) -> float:
        data = sorted(samples or list(self._samples))
        if not data:
            return 0.0
        idx = (p / 100) * (len(data) - 1)
        lower = int(idx)
        upper = min(lower + 1, len(data) - 1)
        frac = idx - lower
        return round(data[lower] * (1 - frac) + data[upper] * frac, 2)

    def p50(self) -> float:
        return self.percentile(50)

    def p90(self) -> float:
        return self.percentile(90)

    def p95(self) -> float:
        return self.percentile(95)

    def p99(self) -> float:
        return self.percentile(99)

    def mean(self) -> float:
        data = list(self._samples)
        return round(sum(data) / max(1, len(data)), 2)

    def std_dev(self) -> float:
        data = list(self._samples)
        if len(data) < 2:
            return 0.0
        m = sum(data) / len(data)
        variance = sum((x - m) ** 2 for x in data) / (len(data) - 1)
        return round(math.sqrt(variance), 2)

    def summary(self) -> Dict:
        data = list(self._samples)
        if not data:
            return {"samples": 0}
        return {
            "samples": len(data),
            "mean_ms": self.mean(),
            "std_dev_ms": self.std_dev(),
            "p50_ms": self.p50(),
            "p90_ms": self.p90(),
            "p95_ms": self.p95(),
            "p99_ms": self.p99(),
            "min_ms": round(min(data), 2),
            "max_ms": round(max(data), 2),
        }

    def operation_summary(self) -> Dict:
        return {
            op: {
                "samples": len(samples),
                "mean_ms": round(sum(samples) / max(1, len(samples)), 2),
                "p95_ms": self.percentile(95, list(samples)),
            }
            for op, samples in self._by_operation.items()
        }
