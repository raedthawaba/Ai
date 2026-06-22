"""Phase 8.9 — Token Usage Tracker: تتبع استخدام التوكنات."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class TokenUsagePoint:
    """نقطة قياس استخدام توكنات."""
    timestamp: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    provider: str
    session_id: Optional[str] = None
    latency_ms: float = 0.0

    @property
    def tokens_per_second(self) -> float:
        if self.latency_ms <= 0:
            return 0.0
        return (self.completion_tokens / self.latency_ms) * 1000


class TokenUsageTracker:
    """
    تتبع وتحليل استخدام التوكنات.

    المميزات:
    - سجل زمني للاستخدام
    - إحصائيات لكل نموذج/مزود
    - حساب tokens/second
    - تنبيهات عند الحدود
    - تقارير بالوقت
    """

    def __init__(
        self,
        window_size: int = 1000,
        alert_daily_limit: Optional[int] = None,
    ):
        self._data: Deque[TokenUsagePoint] = deque(maxlen=window_size)
        self._lock = Lock()
        self._daily_usage: Dict[str, int] = defaultdict(int)
        self._model_totals: Dict[str, int] = defaultdict(int)
        self._provider_totals: Dict[str, int] = defaultdict(int)
        self.alert_daily_limit = alert_daily_limit
        self._total_requests = 0
        self._total_tokens_all_time = 0

    def record(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        provider: str,
        latency_ms: float = 0.0,
        session_id: Optional[str] = None,
    ) -> TokenUsagePoint:
        total = prompt_tokens + completion_tokens
        point = TokenUsagePoint(
            timestamp=time.time(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            model=model,
            provider=provider,
            session_id=session_id,
            latency_ms=latency_ms,
        )
        with self._lock:
            self._data.append(point)
            today = time.strftime("%Y-%m-%d")
            self._daily_usage[today] += total
            self._model_totals[model] += total
            self._provider_totals[provider] += total
            self._total_requests += 1
            self._total_tokens_all_time += total

        if self.alert_daily_limit:
            today = time.strftime("%Y-%m-%d")
            if self._daily_usage.get(today, 0) > self.alert_daily_limit:
                import logging
                logging.getLogger(__name__).warning(
                    "Daily token limit exceeded: %d > %d",
                    self._daily_usage[today], self.alert_daily_limit,
                )
        return point

    def get_summary(self) -> Dict:
        with self._lock:
            data = list(self._data)

        if not data:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "avg_tokens_per_request": 0.0,
                "avg_completion_tokens": 0.0,
                "avg_tokens_per_second": 0.0,
                "by_model": {},
                "by_provider": {},
            }

        total_tokens = sum(d.total_tokens for d in data)
        avg_tps = (
            sum(d.tokens_per_second for d in data if d.tokens_per_second > 0)
            / max(1, sum(1 for d in data if d.tokens_per_second > 0))
        )

        return {
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens_all_time,
            "recent_requests": len(data),
            "recent_tokens": total_tokens,
            "avg_tokens_per_request": round(total_tokens / max(1, len(data)), 1),
            "avg_completion_tokens": round(
                sum(d.completion_tokens for d in data) / max(1, len(data)), 1
            ),
            "avg_tokens_per_second": round(avg_tps, 2),
            "by_model": dict(self._model_totals),
            "by_provider": dict(self._provider_totals),
            "today_usage": self._daily_usage.get(time.strftime("%Y-%m-%d"), 0),
        }

    def get_recent(
        self,
        minutes: int = 60,
    ) -> List[TokenUsagePoint]:
        cutoff = time.time() - (minutes * 60)
        with self._lock:
            return [d for d in self._data if d.timestamp >= cutoff]
