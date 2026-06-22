"""Distributed Cache — multi-layer caching with L1 (local) and L2 (Redis) tiers."""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

import redis

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LRUCache(Generic[T]):
    """Thread-safe in-process LRU cache."""

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, tuple[T, float]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key not in self._cache:
                return None
            value, expires_at = self._cache[key]
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        with self._lock:
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            expires_at = time.time() + ttl if ttl else 0.0
            self._cache[key] = (value, expires_at)
            self._cache.move_to_end(key)

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class DistributedCache:
    """Two-tier cache: L1 (in-process LRU) + L2 (Redis)."""

    def __init__(
        self,
        redis_client: redis.Redis,
        l1_max_size: int = 1000,
        l1_ttl: int = 60,
        l2_ttl: int = 3600,
        namespace: str = "cache",
    ) -> None:
        self.redis = redis_client
        self.l1 = LRUCache(max_size=l1_max_size)
        self.l1_ttl = l1_ttl
        self.l2_ttl = l2_ttl
        self.namespace = namespace
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        namespaced = f"{self.namespace}:{key}"

        value = self.l1.get(namespaced)
        if value is not None:
            self._hits_l1 += 1
            return value

        raw = self.redis.get(namespaced)
        if raw is not None:
            self._hits_l2 += 1
            value = json.loads(raw)
            self.l1.set(namespaced, value, ttl=self.l1_ttl)
            return value

        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        namespaced = f"{self.namespace}:{key}"
        l2_ttl = ttl or self.l2_ttl

        self.l1.set(namespaced, value, ttl=min(l2_ttl, self.l1_ttl))
        self.redis.setex(namespaced, l2_ttl, json.dumps(value, default=str))

    def delete(self, key: str) -> None:
        namespaced = f"{self.namespace}:{key}"
        self.l1.delete(namespaced)
        self.redis.delete(namespaced)

    def get_or_set(
        self,
        key: str,
        func: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        value = self.get(key)
        if value is not None:
            return value
        value = func()
        if value is not None:
            self.set(key, value, ttl)
        return value

    def invalidate_pattern(self, pattern: str) -> int:
        full_pattern = f"{self.namespace}:{pattern}"
        keys = self.redis.keys(full_pattern)
        if keys:
            self.redis.delete(*keys)
        self.l1.clear()
        return len(keys)

    def stats(self) -> Dict[str, Any]:
        total = self._hits_l1 + self._hits_l2 + self._misses
        hit_rate = (self._hits_l1 + self._hits_l2) / total if total > 0 else 0.0
        return {
            "hits_l1": self._hits_l1,
            "hits_l2": self._hits_l2,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "l1_size": self.l1.size,
        }
