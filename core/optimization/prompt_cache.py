"""
Prompt Cache — caches processed prompt prefixes to avoid redundant tokenization
and attention computation for repeated system prompts and few-shot examples.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


@dataclass
class CachedPrefix:
    prefix_hash: str
    prefix_text: str
    prefix_tokens: List[int]
    kv_states: Optional[Any]
    created_at: float = field(default_factory=time.time)
    hit_count: int = 0
    model: str = ""


class PromptCacheManager:
    """Caches tokenized prefix states for reuse across requests."""

    def __init__(
        self,
        redis_client: redis.Redis,
        max_prefix_length: int = 2048,
        ttl_seconds: int = 3600,
    ) -> None:
        self.redis = redis_client
        self.max_prefix_length = max_prefix_length
        self.ttl = ttl_seconds
        self._in_memory: Dict[str, CachedPrefix] = {}
        self._hits = 0
        self._misses = 0

    def cache_prefix(
        self,
        model: str,
        prefix_text: str,
        prefix_tokens: List[int],
        kv_states: Optional[Any] = None,
    ) -> str:
        if len(prefix_tokens) > self.max_prefix_length:
            logger.debug("Prefix too long to cache: %d tokens", len(prefix_tokens))
            return ""

        prefix_hash = self._hash(model, prefix_tokens)

        self._in_memory[prefix_hash] = CachedPrefix(
            prefix_hash=prefix_hash,
            prefix_text=prefix_text,
            prefix_tokens=prefix_tokens,
            kv_states=kv_states,
            model=model,
        )

        meta = {"prefix_hash": prefix_hash, "token_count": len(prefix_tokens), "model": model}
        self.redis.setex(f"prompt_cache:meta:{prefix_hash}", self.ttl, json.dumps(meta))

        logger.debug("Cached prefix %s: %d tokens", prefix_hash[:8], len(prefix_tokens))
        return prefix_hash

    def get_cached_prefix(
        self, model: str, prefix_tokens: List[int]
    ) -> Optional[CachedPrefix]:
        prefix_hash = self._hash(model, prefix_tokens)

        entry = self._in_memory.get(prefix_hash)
        if entry:
            entry.hit_count += 1
            self._hits += 1
            return entry

        meta_raw = self.redis.get(f"prompt_cache:meta:{prefix_hash}")
        if meta_raw:
            self._misses += 1
            return None

        self._misses += 1
        return None

    def find_longest_cached_prefix(
        self, model: str, tokens: List[int], min_len: int = 32
    ) -> Optional[CachedPrefix]:
        for length in range(len(tokens) - 1, min_len - 1, -1):
            prefix = tokens[:length]
            cached = self.get_cached_prefix(model, prefix)
            if cached:
                return cached
        return None

    def invalidate(self, prefix_hash: str) -> None:
        self._in_memory.pop(prefix_hash, None)
        self.redis.delete(f"prompt_cache:meta:{prefix_hash}")

    def _hash(self, model: str, tokens: List[int]) -> str:
        payload = json.dumps({"model": model, "tokens": tokens})
        return hashlib.sha256(payload.encode()).hexdigest()

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "cached_prefixes": len(self._in_memory),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }
