from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple


class EmbeddingCache:
    """LRU in-memory cache for text→embedding pairs."""

    def __init__(self, max_size: int = 10_000) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, Tuple[List[float], float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        key = self._key(text)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key][0]
        self._misses += 1
        return None

    def put(self, text: str, vector: List[float]) -> None:
        key = self._key(text)
        self._cache[key] = (vector, time.time())
        self._cache.move_to_end(key)
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
        }
