"""
KV Cache Manager — manages the key-value cache for transformer attention layers
to avoid redundant computation across requests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    key: str
    past_key_values: Any
    input_ids: List[int]
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    hit_count: int = 0
    size_bytes: int = 0


class KVCacheManager:
    """Manages KV cache with LRU eviction and prefix sharing."""

    def __init__(
        self,
        max_entries: int = 512,
        max_memory_gb: float = 4.0,
        ttl_seconds: int = 300,
    ) -> None:
        self.max_entries = max_entries
        self.max_memory_bytes = int(max_memory_gb * 1024 ** 3)
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}
        self._total_bytes = 0
        self._hits = 0
        self._misses = 0

    def get(self, cache_key: str) -> Optional[Tuple[Any, List[int]]]:
        entry = self._cache.get(cache_key)
        if entry is None:
            self._misses += 1
            return None

        if time.time() - entry.created_at > self.ttl_seconds:
            self._evict(cache_key)
            self._misses += 1
            return None

        entry.last_used = time.time()
        entry.hit_count += 1
        self._hits += 1
        return entry.past_key_values, entry.input_ids

    def store(
        self,
        cache_key: str,
        past_key_values: Any,
        input_ids: List[int],
    ) -> None:
        size_bytes = self._estimate_size(past_key_values)

        while (
            (len(self._cache) >= self.max_entries or
             self._total_bytes + size_bytes > self.max_memory_bytes)
            and self._cache
        ):
            self._evict_lru()

        entry = CacheEntry(
            key=cache_key,
            past_key_values=past_key_values,
            input_ids=input_ids,
            size_bytes=size_bytes,
        )
        self._cache[cache_key] = entry
        self._total_bytes += size_bytes

    def compute_key(self, model: str, input_ids: List[int]) -> str:
        payload = json.dumps({"model": model, "ids": input_ids})
        return hashlib.sha256(payload.encode()).hexdigest()

    def find_prefix_match(
        self,
        model: str,
        input_ids: List[int],
        min_prefix_len: int = 10,
    ) -> Optional[Tuple[Any, List[int], int]]:
        for length in range(len(input_ids) - 1, min_prefix_len - 1, -1):
            prefix = input_ids[:length]
            key = self.compute_key(model, prefix)
            result = self.get(key)
            if result:
                kv, cached_ids = result
                return kv, cached_ids, length
        return None

    def _evict(self, key: str) -> None:
        entry = self._cache.pop(key, None)
        if entry:
            self._total_bytes -= entry.size_bytes
            self._free_kv(entry.past_key_values)

    def _evict_lru(self) -> None:
        if not self._cache:
            return
        lru_key = min(self._cache, key=lambda k: self._cache[k].last_used)
        self._evict(lru_key)

    def _estimate_size(self, past_key_values: Any) -> int:
        try:
            import torch
            total = 0
            for layer in past_key_values:
                for tensor in layer:
                    total += tensor.nelement() * tensor.element_size()
            return total
        except Exception:
            return 1024 * 1024

    def _free_kv(self, past_key_values: Any) -> None:
        try:
            import torch
            for layer in past_key_values:
                for tensor in layer:
                    del tensor
            torch.cuda.empty_cache()
        except Exception:
            pass

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "memory_mb": round(self._total_bytes / 1024**2, 1),
            "max_memory_mb": round(self.max_memory_bytes / 1024**2, 1),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }
