"""Quota Manager — tracks and enforces per-tenant resource limits."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import redis

logger = logging.getLogger(__name__)


@dataclass
class QuotaUsage:
    requests_today: int
    tokens_today: int
    gpu_minutes_used: float
    requests_limit: int
    tokens_limit: int
    gpu_minutes_limit: float
    reset_at: float


class QuotaManager:
    """Enforces per-tenant quotas using Redis atomic counters."""

    def __init__(self, redis_client: redis.Redis, db: Any) -> None:
        self.redis = redis_client
        self.db = db

    def check_and_increment(
        self,
        tenant_id: str,
        operation: str,
        tokens: int = 0,
        gpu_minutes: float = 0.0,
    ) -> Tuple[bool, str]:
        settings = self._get_tenant_settings(tenant_id)
        if not settings:
            return False, "tenant_not_found"

        day_key = f"quota:{tenant_id}:{operation}:{self._day_key()}"
        month_key = f"quota:{tenant_id}:gpu:{self._month_key()}"

        max_requests = settings.get("max_requests_per_day", 100)
        if max_requests != -1:
            current = self.redis.incr(day_key)
            self.redis.expireat(day_key, self._next_midnight())
            if current > max_requests:
                self.redis.decr(day_key)
                return False, f"daily_request_limit_exceeded ({current}/{max_requests})"

        if tokens > 0:
            token_key = f"quota:{tenant_id}:tokens:{self._day_key()}"
            max_tokens_per_req = settings.get("max_tokens_per_request", 4096)
            if max_tokens_per_req != -1 and tokens > max_tokens_per_req:
                return False, f"token_limit_exceeded ({tokens}/{max_tokens_per_req})"

        if gpu_minutes > 0:
            max_gpu = settings.get("gpu_minutes_per_month", 0)
            if max_gpu != -1:
                current_gpu = float(self.redis.incrbyfloat(month_key, gpu_minutes))
                self.redis.expireat(month_key, self._next_month())
                if current_gpu > max_gpu:
                    self.redis.incrbyfloat(month_key, -gpu_minutes)
                    return False, f"gpu_quota_exceeded ({current_gpu:.1f}/{max_gpu})"

        return True, "allowed"

    def get_usage(self, tenant_id: str) -> QuotaUsage:
        settings = self._get_tenant_settings(tenant_id) or {}
        day_key = f"quota:{tenant_id}:inference:{self._day_key()}"
        month_key = f"quota:{tenant_id}:gpu:{self._month_key()}"

        return QuotaUsage(
            requests_today=int(self.redis.get(day_key) or 0),
            tokens_today=int(self.redis.get(f"quota:{tenant_id}:tokens:{self._day_key()}") or 0),
            gpu_minutes_used=float(self.redis.get(month_key) or 0),
            requests_limit=settings.get("max_requests_per_day", 100),
            tokens_limit=settings.get("max_tokens_per_request", 4096),
            gpu_minutes_limit=settings.get("gpu_minutes_per_month", 0),
            reset_at=self._next_midnight(),
        )

    def _get_tenant_settings(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        cached = self.redis.get(f"tenant:{tenant_id}")
        if cached:
            import json
            data = json.loads(cached)
            return data.get("settings", {})
        row = self.db.fetchone("SELECT settings FROM tenants WHERE tenant_id = %s", (tenant_id,))
        if row:
            import json
            return json.loads(row["settings"])
        return None

    def _day_key(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    def _month_key(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y%m")

    def _next_midnight(self) -> int:
        import math
        seconds_per_day = 86400
        return math.ceil(time.time() / seconds_per_day) * seconds_per_day

    def _next_month(self) -> int:
        from datetime import datetime, timezone
        from calendar import monthrange
        now = datetime.now(timezone.utc)
        days = monthrange(now.year, now.month)[1]
        return int(now.replace(day=days, hour=23, minute=59, second=59).timestamp())
