"""Phase 8.3 — Token Tracker: تتبع استخدام التوكنات."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional


@dataclass
class TokenUsageRecord:
    """سجل استخدام توكنات لطلب واحد."""
    request_id: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class TokenStats:
    """إحصائيات إجمالية للتوكنات."""
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    avg_tokens_per_request: float = 0.0
    avg_latency_ms: float = 0.0
    by_model: Dict[str, int] = field(default_factory=dict)
    by_provider: Dict[str, int] = field(default_factory=dict)


class TokenTracker:
    """
    تتبع استخدام التوكنات عبر جميع الطلبات.

    المهام:
    - تسجيل استخدام كل طلب
    - إحصائيات مجمّعة
    - تتبع حسب النموذج والمزود
    - تنبيه عند الحدود
    """

    def __init__(
        self,
        max_records: int = 10000,
        alert_threshold: Optional[int] = None,
    ):
        self._records: List[TokenUsageRecord] = []
        self._lock = Lock()
        self.max_records = max_records
        self.alert_threshold = alert_threshold
        self._total_tokens = 0
        self._by_model: Dict[str, int] = defaultdict(int)
        self._by_provider: Dict[str, int] = defaultdict(int)
        self._total_latency_ms = 0.0
        self._request_count = 0

    def record(
        self,
        request_id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float = 0.0,
        session_id: Optional[str] = None,
    ) -> TokenUsageRecord:
        """تسجيل استخدام توكنات."""
        total = prompt_tokens + completion_tokens
        record = TokenUsageRecord(
            request_id=request_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            session_id=session_id,
            latency_ms=latency_ms,
        )

        with self._lock:
            self._records.append(record)
            if len(self._records) > self.max_records:
                self._records = self._records[-self.max_records:]

            self._total_tokens += total
            self._by_model[model] += total
            self._by_provider[provider] += total
            self._total_latency_ms += latency_ms
            self._request_count += 1

        if self.alert_threshold and self._total_tokens > self.alert_threshold:
            import logging
            logging.getLogger(__name__).warning(
                "Token usage alert: %d tokens used (threshold: %d)",
                self._total_tokens, self.alert_threshold,
            )

        return record

    def get_stats(self) -> TokenStats:
        """الحصول على إحصائيات إجمالية."""
        with self._lock:
            if self._request_count == 0:
                return TokenStats()

            total_prompt = sum(r.prompt_tokens for r in self._records)
            total_completion = sum(r.completion_tokens for r in self._records)

            return TokenStats(
                total_requests=self._request_count,
                total_prompt_tokens=total_prompt,
                total_completion_tokens=total_completion,
                total_tokens=self._total_tokens,
                avg_tokens_per_request=self._total_tokens / self._request_count,
                avg_latency_ms=self._total_latency_ms / self._request_count,
                by_model=dict(self._by_model),
                by_provider=dict(self._by_provider),
            )

    def get_session_usage(self, session_id: str) -> Dict[str, int]:
        """إجمالي التوكنات لجلسة معينة."""
        with self._lock:
            records = [r for r in self._records if r.session_id == session_id]
        return {
            "prompt": sum(r.prompt_tokens for r in records),
            "completion": sum(r.completion_tokens for r in records),
            "total": sum(r.total_tokens for r in records),
            "requests": len(records),
        }

    def reset(self) -> None:
        """إعادة تعيين جميع الإحصائيات."""
        with self._lock:
            self._records.clear()
            self._total_tokens = 0
            self._by_model.clear()
            self._by_provider.clear()
            self._total_latency_ms = 0.0
            self._request_count = 0
