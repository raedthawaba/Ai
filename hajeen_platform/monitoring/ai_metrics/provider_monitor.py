"""Phase 8.9 — Provider Monitor: مراقبة مزودي LLM."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional


@dataclass
class ProviderEvent:
    """حدث مزود واحد."""
    timestamp: float
    provider: str
    event_type: str  # "success" | "failure" | "timeout" | "fallback"
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    model: str = ""


@dataclass
class ProviderHealth:
    """صحة مزود واحد."""
    provider: str
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    fallback_count: int = 0
    avg_latency_ms: float = 0.0
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    is_healthy: bool = True

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 100.0
        return round((self.success_count / self.total_requests) * 100, 2)

    @property
    def error_rate(self) -> float:
        return round(100.0 - self.success_rate, 2)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "success_rate_pct": self.success_rate,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "is_healthy": self.is_healthy,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
        }


class ProviderMonitor:
    """
    مراقبة مزودي LLM.

    يتتبع:
    - معدل النجاح/الفشل
    - زمن الاستجابة
    - حالات Fallback
    - حالة الصحة
    """

    def __init__(
        self,
        unhealthy_threshold: float = 50.0,
        window_size: int = 200,
    ):
        self._providers: Dict[str, ProviderHealth] = {}
        self._events: List[ProviderEvent] = []
        self._lock = Lock()
        self.unhealthy_threshold = unhealthy_threshold
        self.window_size = window_size
        self._latency_sums: Dict[str, float] = defaultdict(float)

    def _get_or_create(self, provider: str) -> ProviderHealth:
        if provider not in self._providers:
            self._providers[provider] = ProviderHealth(provider=provider)
        return self._providers[provider]

    def record_success(
        self,
        provider: str,
        latency_ms: float,
        model: str = "",
    ) -> None:
        with self._lock:
            health = self._get_or_create(provider)
            health.total_requests += 1
            health.success_count += 1
            health.last_success = time.time()
            self._latency_sums[provider] += latency_ms
            health.avg_latency_ms = self._latency_sums[provider] / health.success_count
            health.is_healthy = health.success_rate >= self.unhealthy_threshold

            self._events.append(ProviderEvent(
                timestamp=time.time(),
                provider=provider,
                event_type="success",
                latency_ms=latency_ms,
                model=model,
            ))
            if len(self._events) > self.window_size:
                self._events = self._events[-self.window_size:]

    def record_failure(
        self,
        provider: str,
        error: str = "",
        is_timeout: bool = False,
    ) -> None:
        with self._lock:
            health = self._get_or_create(provider)
            health.total_requests += 1
            health.failure_count += 1
            health.last_failure = time.time()
            if is_timeout:
                health.timeout_count += 1
            health.is_healthy = health.success_rate >= self.unhealthy_threshold

            import logging
            if not health.is_healthy:
                logging.getLogger(__name__).warning(
                    "Provider '%s' is UNHEALTHY (success_rate=%.1f%%)",
                    provider, health.success_rate,
                )

    def record_fallback(self, from_provider: str, to_provider: str) -> None:
        with self._lock:
            health = self._get_or_create(from_provider)
            health.fallback_count += 1
            import logging
            logging.getLogger(__name__).info(
                "Fallback: %s → %s", from_provider, to_provider
            )

    def get_provider_health(self, provider: str) -> Optional[ProviderHealth]:
        return self._providers.get(provider)

    def get_all_health(self) -> Dict[str, dict]:
        with self._lock:
            return {name: h.to_dict() for name, h in self._providers.items()}

    def get_healthy_providers(self) -> List[str]:
        with self._lock:
            return [
                name for name, h in self._providers.items()
                if h.is_healthy
            ]

    def get_summary(self) -> Dict:
        with self._lock:
            total = sum(h.total_requests for h in self._providers.values())
            successes = sum(h.success_count for h in self._providers.values())
        return {
            "total_providers": len(self._providers),
            "healthy_providers": len(self.get_healthy_providers()),
            "total_requests": total,
            "overall_success_rate": round(
                (successes / max(1, total)) * 100, 2
            ),
            "providers": self.get_all_health(),
        }
