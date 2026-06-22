"""FAISS Vector Store — بحث تشابه حقيقي عبر FAISS."""
from __future__ import annotations

import json
import logging
import os
import pickle
from typing import Dict, List, Optional

import numpy as np

from data_engine.storage.vector_store.base_vector_store import (
    BaseVectorStore,
    SearchResult,
    VectorEntry,
    VectorStoreStats,
)

logger = logging.getLogger(__name__)


class FAISSVectorStore(BaseVectorStore):
    """
    Vector store مبني على FAISS مع:
    - IndexFlatIP للبحث الدقيق (Exact Inner Product / Cosine إذا كانت vectors مُعيَّارة)
    - metadata store موازٍ في ذاكرة + حفظ pickle
    """

    def __init__(self, dimensions: int = 384, index_type: str = "flat_ip"):
        self.dimensions = dimensions
        self.index_type = index_type
        self._index = None
        self._entries: Dict[int, VectorEntry] = {}
        self._id_to_faiss: Dict[str, int] = {}
        self._faiss_counter = 0
        self._init_index()

    def _init_index(self) -> None:
        import faiss
        if self.index_type == "flat_ip":
            self._index = faiss.IndexFlatIP(self.dimensions)
        elif self.index_type == "flat_l2":
            self._index = faiss.IndexFlatL2(self.dimensions)
        elif self.index_type == "ivf":
            quantizer = faiss.IndexFlatIP(self.dimensions)
            self._index = faiss.IndexIVFFlat(quantizer, self.dimensions, 100)
        else:
            self._index = faiss.IndexFlatIP(self.dimensions)
        logger.debug(f"FAISS index جاهز: {self.index_type} dims={self.dimensions}")

    def _to_numpy(self, vectors: List[List[float]]) -> np.ndarray:
        arr = np.array(vectors, dtype=np.float32)
        # تعيير L2 لضمان cosine similarity مع IndexFlatIP
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (arr / norms).astype(np.float32)

    def add(self, entries: List[VectorEntry]) -> int:
        if not entries:
            return 0
        vectors = [e.vector for e in entries]
        arr = self._to_numpy(vectors)

        # IVF يحتاج training
        if hasattr(self._index, "is_trained") and not self._index.is_trained:
            if arr.shape[0] >= 100:
                self._index.train(arr)
            else:
                # fallback إلى FlatIP
                import faiss
                self._index = faiss.IndexFlatIP(self.dimensions)

        start_id = self._faiss_counter
        self._index.add(arr)

        for i, entry in enumerate(entries):
            faiss_id = start_id + i
            self._entries[faiss_id] = entry
            self._id_to_faiss[entry.id] = faiss_id

        self._faiss_counter += len(entries)
        logger.debug(f"أُضيف {len(entries)} vectors — المجموع: {self._faiss_counter}")
        return len(entries)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[SearchResult]:
        if self._index is None or self._faiss_counter == 0:
            return []

        k = min(top_k * 3 if filter_metadata else top_k, self._faiss_counter)
        q_arr = self._to_numpy([query_vector])

        scores, indices = self._index.search(q_arr, k)
        scores = scores[0].tolist()
        indices = indices[0].tolist()

        results: List[SearchResult] = []
        for score, idx in zip(scores, indices):
            if idx < 0 or idx not in self._entries:
                continue
            entry = self._entries[idx]
            if filter_metadata:
                match = all(
                    entry.metadata.get(key) == val
                    for key, val in filter_metadata.items()
                )
                if not match:
                    continue
            results.append(SearchResult(
                chunk_id=entry.chunk_id,
                article_id=entry.article_id,
                score=float(score),
                text=entry.text,
                model_name=entry.model_name,
                metadata=entry.metadata,
            ))
            if len(results) >= top_k:
                break

        return results

    def delete(self, ids: List[str]) -> int:
        deleted = 0
        for vid in ids:
            if vid in self._id_to_faiss:
                faiss_id = self._id_to_faiss.pop(vid)
                self._entries.pop(faiss_id, None)
                deleted += 1
        return deleted

    def stats(self) -> VectorStoreStats:
        return VectorStoreStats(
            total_vectors=self._faiss_counter,
            index_type=f"faiss:{self.index_type}",
            dimensions=self.dimensions,
            is_trained=getattr(self._index, "is_trained", True),
            extra={"in_memory_entries": len(self._entries)},
        )

    def save(self, path: str) -> None:
        import faiss
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        faiss.write_index(self._index, path + ".faiss")
        meta = {
            "entries": self._entries,
            "id_to_faiss": self._id_to_faiss,
            "faiss_counter": self._faiss_counter,
            "dimensions": self.dimensions,
            "index_type": self.index_type,
        }
        with open(path + ".meta", "wb") as f:
            pickle.dump(meta, f)
        logger.info(f"FAISS index حُفظ في: {path}")

    def load(self, path: str) -> None:
        import faiss
        if not os.path.exists(path + ".faiss"):
            raise FileNotFoundError(f"لا يوجد FAISS index في: {path}")
        self._index = faiss.read_index(path + ".faiss")
        with open(path + ".meta", "rb") as f:
            meta = pickle.load(f)
        self._entries = meta["entries"]
        self._id_to_faiss = meta["id_to_faiss"]
        self._faiss_counter = meta["faiss_counter"]
        self.dimensions = meta["dimensions"]
        self.index_type = meta["index_type"]
        logger.info(f"FAISS index مُحمَّل: {self._faiss_counter} vectors")
