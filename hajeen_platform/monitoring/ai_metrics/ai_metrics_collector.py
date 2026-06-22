"""Phase 8.9 — AI Metrics Collector: جامع مركزي لمقاييس AI."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .token_usage_tracker import TokenUsageTracker
from .latency_tracker import LatencyTracker
from .provider_monitor import ProviderMonitor

logger = logging.getLogger(__name__)

_metrics_instance: Optional["AIMetricsCollector"] = None


@dataclass
class AIEvent:
    """حدث AI مركزي."""
    event_id: str
    event_type: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)


class AIMetricsCollector:
    """
    جامع مركزي لجميع مقاييس AI.

    يجمع:
    - Token usage
    - Latency tracking
    - Provider health
    - Streaming metrics
    - Memory usage
    - Prompt statistics
    - Inference timing
    """

    def __init__(self):
        self.tokens = TokenUsageTracker()
        self.latency = LatencyTracker()
        self.providers = ProviderMonitor()
        self._events: List[AIEvent] = []
        self._max_events = 1000
        self._start_time = time.time()

        # Prompt stats
        self._prompt_stats = {
            "total_prompts": 0,
            "total_prompt_tokens": 0,
            "total_context_injections": 0,
            "avg_prompt_length": 0.0,
            "language_distribution": {},
        }

        # Streaming stats
        self._stream_stats = {
            "total_streams": 0,
            "total_chunks": 0,
            "cancelled_streams": 0,
            "avg_chunks_per_stream": 0.0,
        }

        # Memory stats
        self._memory_stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "total_messages": 0,
            "summarizations": 0,
        }

    def record_inference(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        session_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """تسجيل حدث inference."""
        if success:
            self.tokens.record(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=model,
                provider=provider,
                latency_ms=latency_ms,
                session_id=session_id,
            )
            self.latency.record(
                latency_ms=latency_ms,
                operation="inference",
                model=model,
                provider=provider,
                success=True,
            )
            self.providers.record_success(
                provider=provider,
                latency_ms=latency_ms,
                model=model,
            )
        else:
            self.latency.record(
                latency_ms=latency_ms,
                operation="inference",
                model=model,
                provider=provider,
                success=False,
            )
            self.providers.record_failure(
                provider=provider,
                error=error or "",
            )

    def record_rag(
        self,
        query: str,
        retrieval_ms: float,
        chunks_found: int,
        success: bool = True,
    ) -> None:
        """تسجيل حدث RAG."""
        self.latency.record(
            latency_ms=retrieval_ms,
            operation="rag",
            success=success,
        )

    def record_stream(
        self,
        chunks_count: int,
        total_chars: int,
        duration_ms: float,
        cancelled: bool = False,
    ) -> None:
        """تسجيل حدث streaming."""
        self._stream_stats["total_streams"] += 1
        self._stream_stats["total_chunks"] += chunks_count
        if cancelled:
            self._stream_stats["cancelled_streams"] += 1
        total_streams = self._stream_stats["total_streams"]
        if total_streams > 0:
            self._stream_stats["avg_chunks_per_stream"] = (
                self._stream_stats["total_chunks"] / total_streams
            )

    def record_prompt(
        self,
        prompt_tokens: int,
        language: str = "ar",
        context_injected: bool = False,
    ) -> None:
        """تسجيل إحصائيات prompt."""
        self._prompt_stats["total_prompts"] += 1
        self._prompt_stats["total_prompt_tokens"] += prompt_tokens
        if context_injected:
            self._prompt_stats["total_context_injections"] += 1

        lang_dist = self._prompt_stats["language_distribution"]
        lang_dist[language] = lang_dist.get(language, 0) + 1

        total = self._prompt_stats["total_prompts"]
        total_tokens = self._prompt_stats["total_prompt_tokens"]
        self._prompt_stats["avg_prompt_length"] = total_tokens / max(1, total)

    def record_session(
        self,
        active_sessions: int,
        total_messages: int,
    ) -> None:
        """تحديث إحصائيات الجلسات."""
        self._memory_stats["active_sessions"] = active_sessions
        self._memory_stats["total_messages"] = total_messages

    def get_full_report(self) -> Dict[str, Any]:
        """تقرير شامل لجميع المقاييس."""
        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": round(uptime, 1),
            "phase": "8 — LLM Inference + AI Runtime",
            "tokens": self.tokens.get_summary(),
            "latency": {
                "overall": self.latency.get_stats(),
                "by_operation": self.latency.get_by_operation(),
            },
            "providers": self.providers.get_summary(),
            "prompts": self._prompt_stats,
            "streaming": self._stream_stats,
            "memory": self._memory_stats,
        }

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """مقاييس مختصرة للـ dashboard."""
        token_summary = self.tokens.get_summary()
        latency_stats = self.latency.get_stats()
        provider_summary = self.providers.get_summary()

        return {
            "total_requests": token_summary["total_requests"],
            "total_tokens": token_summary["total_tokens"],
            "avg_latency_ms": latency_stats.get("avg_ms", 0.0),
            "p95_latency_ms": latency_stats.get("p95_ms", 0.0),
            "provider_health": provider_summary["overall_success_rate"],
            "healthy_providers": provider_summary["healthy_providers"],
            "active_sessions": self._memory_stats["active_sessions"],
            "stream_count": self._stream_stats["total_streams"],
        }


def get_ai_metrics() -> AIMetricsCollector:
    """Singleton instance لـ AIMetricsCollector."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = AIMetricsCollector()
    return _metrics_instance
