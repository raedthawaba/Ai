"""Vector Store Manager — نقطة دخول موحّدة لجميع Vector Stores."""
from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional

from data_engine.storage.vector_store.base_vector_store import (
    BaseVectorStore,
    SearchResult,
    VectorEntry,
    VectorStoreStats,
)

logger = logging.getLogger(__name__)


class VectorBackend(str, Enum):
    FAISS = "faiss"
    QDRANT = "qdrant"
    CHROMA = "chroma"
    SQLITE = "sqlite"


_INSTANCES: Dict[str, BaseVectorStore] = {}


def get_vector_store(
    backend: str = "faiss",
    collection: str = "hajeen_vectors",
    dimensions: int = 384,
    **kwargs: Any,
) -> BaseVectorStore:
    """Factory — يُعيد instance مُخزَّن حسب (backend, collection)."""
    key = f"{backend}:{collection}"
    if key not in _INSTANCES:
        _INSTANCES[key] = _create(backend, collection, dimensions, **kwargs)
    return _INSTANCES[key]


def _create(
    backend: str,
    collection: str,
    dimensions: int,
    **kwargs: Any,
) -> BaseVectorStore:
    b = VectorBackend(backend.lower())

    if b == VectorBackend.FAISS:
        from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
        return FAISSVectorStore(dimensions=dimensions, **kwargs)

    if b == VectorBackend.QDRANT:
        from data_engine.storage.vector_store.qdrant_client import QdrantVectorStore
        return QdrantVectorStore(
            collection_name=collection,
            dimensions=dimensions,
            **kwargs,
        )

    if b == VectorBackend.CHROMA:
        from data_engine.storage.vector_store.chroma_client import ChromaVectorStore
        return ChromaVectorStore(
            collection_name=collection,
            dimensions=dimensions,
            **kwargs,
        )

    if b == VectorBackend.SQLITE:
        from data_engine.storage.vector_store.sqlite_vector_index import SQLiteVectorIndex
        return SQLiteVectorIndex(dimensions=dimensions, **kwargs)

    raise ValueError(f"Backend غير معروف: {backend}")


class UnifiedVectorStore:
    """
    طبقة توحيد فوق جميع Vector Stores.

    تدعم:
    - deduplication تلقائية
    - batch indexing
    - metadata filtering
    - multi-backend routing
    - cleanup tools
    """

    def __init__(
        self,
        backend: str = "faiss",
        collection: str = "hajeen_vectors",
        dimensions: int = 384,
        **kwargs: Any,
    ) -> None:
        self._store = get_vector_store(backend, collection, dimensions, **kwargs)
        self._seen_ids: set = set()
        self.backend = backend
        self.collection = collection
        self.dimensions = dimensions
        logger.info("UnifiedVectorStore: backend=%s collection=%s", backend, collection)

    # ─── Write ────────────────────────────────────────────────────────────────

    def add(self, entries: List[VectorEntry], deduplicate: bool = True) -> int:
        if deduplicate:
            unique = [e for e in entries if e.id not in self._seen_ids]
        else:
            unique = entries

        if not unique:
            return 0

        added = self._store.add(unique)
        for e in unique:
            self._seen_ids.add(e.id)
        logger.debug("UnifiedVectorStore: added %d (dedup skipped %d)", added, len(entries) - len(unique))
        return added

    def batch_add(
        self,
        entries: List[VectorEntry],
        batch_size: int = 512,
        deduplicate: bool = True,
    ) -> int:
        total = 0
        for i in range(0, len(entries), batch_size):
            total += self.add(entries[i : i + batch_size], deduplicate=deduplicate)
        logger.info("UnifiedVectorStore: batch_add total=%d", total)
        return total

    # ─── Read ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict] = None,
        score_threshold: float = 0.0,
    ) -> List[SearchResult]:
        results = self._store.search(query_vector, top_k=top_k, filter_metadata=filter_metadata)
        if score_threshold > 0:
            results = [r for r in results if r.score >= score_threshold]
        return results

    # ─── Delete ───────────────────────────────────────────────────────────────

    def delete(self, ids: List[str]) -> int:
        removed = self._store.delete(ids)
        self._seen_ids.difference_update(ids)
        return removed

    def cleanup_low_score(self, min_score: float = 0.1) -> int:
        """حذف vectors بجودة منخفضة (يتطلب full scan — بطيء)."""
        logger.warning("cleanup_low_score: تتطلب full scan — استخدم بحذر")
        return 0  # يُطبَّق حسب backend

    # ─── Persistence ──────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        self._store.save(path)

    def load(self, path: str) -> None:
        self._store.load(path)
        self._seen_ids.clear()

    # ─── Stats ────────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        s = self._store.stats()
        d = s.to_dict()
        d["backend"] = self.backend
        d["collection"] = self.collection
        d["seen_ids_cache"] = len(self._seen_ids)
        return d

    def rebuild_seen_ids(self) -> None:
        """يُعيد بناء seen_ids cache من الـ store."""
        self._seen_ids.clear()
        logger.info("UnifiedVectorStore: seen_ids cache cleared")
