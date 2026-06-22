"""Rate Limiter — sliding window rate limiting using Redis."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import redis

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    requests: int
    window_seconds: int
    burst: int = 0


RATE_LIMITS: Dict[str, RateLimitConfig] = {
    "default": RateLimitConfig(requests=100, window_seconds=60),
    "inference": RateLimitConfig(requests=20, window_seconds=60, burst=5),
    "training": RateLimitConfig(requests=5, window_seconds=3600),
    "embedding": RateLimitConfig(requests=200, window_seconds=60, burst=50),
    "admin": RateLimitConfig(requests=1000, window_seconds=60),
}


class RateLimiter:
    """Sliding window rate limiter backed by Redis."""

    SCRIPT = """
    local key = KEYS[1]
    local window = tonumber(ARGV[1])
    local limit = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local cutoff = now - window * 1000

    redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
    local count = redis.call('ZCARD', key)

    if count < limit then
        redis.call('ZADD', key, now, now .. ':' .. math.random(1, 1000000))
        redis.call('PEXPIRE', key, window * 1000)
        return {1, count + 1, limit}
    else
        return {0, count, limit}
    end
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client
        self._script = redis_client.register_script(self.SCRIPT)

    def check(
        self,
        identifier: str,
        endpoint: str = "default",
        tenant_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, int]]:
        config = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
        limit = config.requests + config.burst

        key_parts = [identifier, endpoint]
        if tenant_id:
            key_parts.append(tenant_id)
        key = "rl:" + hashlib.sha256(":".join(key_parts).encode()).hexdigest()[:16]

        now_ms = int(time.time() * 1000)
        allowed, current, max_req = self._script(
            keys=[key],
            args=[config.window_seconds, limit, now_ms],
        )

        reset_at = int(time.time()) + config.window_seconds
        return bool(allowed), {
            "limit": max_req,
            "remaining": max(0, max_req - current),
            "reset": reset_at,
            "current": current,
        }
