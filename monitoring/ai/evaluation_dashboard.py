from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .inference_metrics import InferenceMetrics
from .token_metrics import TokenMetrics
from .latency_tracker import LatencyTracker
from .gpu_monitor import GPUMonitor
from .hallucination_tracker import HallucinationTracker


class AIEvaluationDashboard:
    """Unified dashboard for all AI performance metrics."""

    _instance: Optional["AIEvaluationDashboard"] = None

    def __init__(self) -> None:
        self.inference = InferenceMetrics()
        self.tokens = TokenMetrics()
        self.latency = LatencyTracker()
        self.gpu = GPUMonitor()
        self.hallucination = HallucinationTracker()
        self._start_time = time.time()

    @classmethod
    def get_instance(cls) -> "AIEvaluationDashboard":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record_inference(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        request_id: str = "",
        session_id: Optional[str] = None,
    ) -> None:
        if success:
            self.inference.record_success(model_id, prompt_tokens, completion_tokens, latency_ms, request_id)
            self.tokens.record(model_id, prompt_tokens, completion_tokens, session_id)
            self.latency.record(latency_ms, operation="inference")
        else:
            self.inference.record_error(model_id, error or "unknown", request_id)

    def check_hallucination(
        self,
        query: str,
        response: str,
        context: Optional[str] = None,
        request_id: str = "",
    ) -> Dict:
        record = self.hallucination.check(query, response, context, request_id)
        return {
            "score": record.score,
            "flags": record.flags,
            "flagged": bool(record.flags),
        }

    def full_report(self) -> Dict:
        return {
            "generated_at": time.time(),
            "uptime_seconds": round(time.time() - self._start_time, 2),
            "inference": self.inference.summary(),
            "tokens": self.tokens.overall_summary(),
            "latency": self.latency.summary(),
            "gpu": self.gpu.summary(),
            "hallucination": self.hallucination.summary(),
            "models": self.inference.by_model(),
            "daily_tokens": self.tokens.daily_summary(),
        }

    def quick_summary(self) -> Dict:
        return {
            "requests": self.inference.summary().get("total_requests", 0),
            "errors": self.inference.summary().get("total_errors", 0),
            "avg_latency_ms": self.latency.mean(),
            "p95_latency_ms": self.latency.p95(),
            "total_tokens": self.tokens.total_tokens(),
            "tps": self.tokens.tokens_per_second(),
            "hallucination_rate": self.hallucination.summary().get("flag_rate", 0.0),
        }
