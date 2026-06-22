from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass
class InferenceRecord:
    request_id: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None


class InferenceMetrics:
    """Track and aggregate inference request metrics."""

    def __init__(self, window_size: int = 1000) -> None:
        self._records: Deque[InferenceRecord] = deque(maxlen=window_size)
        self._total_requests = 0
        self._total_errors = 0

    def record(self, record: InferenceRecord) -> None:
        self._records.append(record)
        self._total_requests += 1
        if not record.success:
            self._total_errors += 1

    def record_success(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        request_id: str = "",
    ) -> None:
        self.record(
            InferenceRecord(
                request_id=request_id,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                success=True,
            )
        )

    def record_error(self, model_id: str, error: str, request_id: str = "") -> None:
        self.record(
            InferenceRecord(
                request_id=request_id,
                model_id=model_id,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
                success=False,
                error=error,
            )
        )

    def summary(self) -> Dict:
        if not self._records:
            return {"total_requests": 0}
        records = list(self._records)
        successful = [r for r in records if r.success]
        latencies = [r.latency_ms for r in successful]
        tokens = [r.completion_tokens for r in successful]
        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": round(self._total_errors / max(1, self._total_requests), 4),
            "window_requests": len(records),
            "avg_latency_ms": round(sum(latencies) / max(1, len(latencies)), 2),
            "avg_completion_tokens": round(sum(tokens) / max(1, len(tokens)), 2),
            "total_completion_tokens": sum(tokens),
        }

    def by_model(self) -> Dict[str, Dict]:
        model_data: Dict[str, List[InferenceRecord]] = {}
        for r in self._records:
            model_data.setdefault(r.model_id, []).append(r)
        return {
            model: {
                "requests": len(recs),
                "errors": sum(1 for r in recs if not r.success),
                "avg_latency_ms": round(
                    sum(r.latency_ms for r in recs if r.success) / max(1, sum(1 for r in recs if r.success)), 2
                ),
            }
            for model, recs in model_data.items()
        }
