"""
Load Balancer — distributes inference requests across model replicas
using weighted round-robin with health awareness.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackendEndpoint:
    url: str
    weight: int = 1
    healthy: bool = True
    active_requests: int = 0
    total_requests: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0
    last_health_check: float = field(default_factory=time.time)

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_errors / self.total_requests

    def record_latency(self, latency_ms: float) -> None:
        alpha = 0.1
        if self.avg_latency_ms == 0:
            self.avg_latency_ms = latency_ms
        else:
            self.avg_latency_ms = (1 - alpha) * self.avg_latency_ms + alpha * latency_ms


class LoadBalancer:
    """Routes requests to the best available inference backend."""

    def __init__(self, model_pool: Any) -> None:
        self.model_pool = model_pool
        self._backends: Dict[str, List[BackendEndpoint]] = {}
        self._rr_counters: Dict[str, int] = {}

    def register_backend(self, model: str, url: str, weight: int = 1) -> None:
        if model not in self._backends:
            self._backends[model] = []
            self._rr_counters[model] = 0
        self._backends[model].append(BackendEndpoint(url=url, weight=weight))
        logger.info("Registered backend %s for model %s (weight=%d)", url, model, weight)

    def get_backend(self, model: str) -> Optional[BackendEndpoint]:
        if model not in self._backends:
            return None

        healthy = [b for b in self._backends[model] if b.healthy]
        if not healthy:
            logger.warning("No healthy backends for model %s", model)
            return None

        # Least-connections among healthy backends
        return min(healthy, key=lambda b: b.active_requests / b.weight)

    def mark_unhealthy(self, url: str) -> None:
        for backends in self._backends.values():
            for backend in backends:
                if backend.url == url:
                    backend.healthy = False
                    logger.warning("Marked backend unhealthy: %s", url)

    def mark_healthy(self, url: str) -> None:
        for backends in self._backends.values():
            for backend in backends:
                if backend.url == url:
                    backend.healthy = True
                    logger.info("Marked backend healthy: %s", url)

    def get_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        for model, backends in self._backends.items():
            stats[model] = [
                {
                    "url": b.url,
                    "healthy": b.healthy,
                    "active_requests": b.active_requests,
                    "total_requests": b.total_requests,
                    "error_rate": round(b.error_rate, 4),
                    "avg_latency_ms": round(b.avg_latency_ms, 2),
                }
                for b in backends
            ]
        return stats
