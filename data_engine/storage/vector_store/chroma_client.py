"""ChromaDB Vector Store Client — إنتاجي مع persistence حقيقي."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

from data_engine.storage.vector_store.base_vector_store import (
    BaseVectorStore,
    SearchResult,
    VectorEntry,
    VectorStoreStats,
)

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = "hajeen_vectors"
_DEFAULT_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./storage_data/chroma")


class ChromaVectorStore(BaseVectorStore):
    """
    ChromaDB vector store مع:
    - persistent storage على القرص
    - collection management
    - deduplication
    - metadata filtering
    - cosine similarity
    """

    def __init__(
        self,
        collection_name: str = _DEFAULT_COLLECTION,
        dimensions: int = 384,
        persist_dir: str = _DEFAULT_PERSIST_DIR,
        in_memory: bool = False,
    ) -> None:
        self.collection_name = collection_name
        self.dimensions = dimensions
        self.persist_dir = persist_dir
        self.in_memory = in_memory
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None
        self._connect()

    # ─── Connection ──────────────────────────────────────────────────────────

    def _connect(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings

            if self.in_memory:
                self._client = chromadb.EphemeralClient()
            else:
                os.makedirs(self.persist_dir, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=self.persist_dir,
                    settings=Settings(anonymized_telemetry=False),
                )

            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine", "dimensions": self.dimensions},
            )
            logger.info(
                "Chroma متصل: collection='%s' persist='%s'",
                self.collection_name,
                self.persist_dir if not self.in_memory else "memory",
            )
        except ImportError:
            raise RuntimeError("chromadb غير مثبّت — pip install chromadb")
        except Exception as exc:
            logger.error("فشل الاتصال بـ Chroma: %s", exc)
            raise

    @staticmethod
    def _stable_id(entry_id: str) -> str:
        """توليد ID ثابت لـ ChromaDB (يجب أن يكون string فريد)."""
        return hashlib.sha1(entry_id.encode()).hexdigest()[:32]

    # ─── CRUD ─────────────────────────────────────────────────────────────────

    def add(self, entries: List[VectorEntry]) -> int:
        if not entries or self._collection is None:
            return 0

        ids, embeddings, metadatas, documents = [], [], [], []
        for entry in entries:
            ids.append(self._stable_id(entry.id))
            embeddings.append(entry.vector)
            documents.append(entry.text or "")
            meta = {
                "chunk_id": entry.chunk_id,
                "article_id": entry.article_id,
                "model_name": entry.model_name,
            }
            # ChromaDB لا يدعم nested dicts — نُسطّح
            for k, v in entry.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
            metadatas.append(meta)

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        logger.debug("Chroma: أُضيف %d vectors", len(ids))
        return len(ids)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[SearchResult]:
        if self._collection is None:
            return []

        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": min(top_k, max(self._collection.count(), 1)),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata:
            # ChromaDB where filter
            if len(filter_metadata) == 1:
                k, v = next(iter(filter_metadata.items()))
                kwargs["where"] = {k: {"$eq": v}}
            else:
                kwargs["where"] = {
                    "$and": [{k: {"$eq": v}} for k, v in filter_metadata.items()]
                }

        try:
            raw = self._collection.query(**kwargs)
        except Exception as exc:
            logger.error("Chroma search error: %s", exc)
            return []

        results = []
        ids_list = raw.get("ids", [[]])[0]
        docs_list = raw.get("documents", [[]])[0]
        metas_list = raw.get("metadatas", [[]])[0]
        dists_list = raw.get("distances", [[]])[0]

        for doc_id, doc, meta, dist in zip(ids_list, docs_list, metas_list, dists_list):
            # ChromaDB cosine distance: score = 1 - distance
            score = max(0.0, 1.0 - float(dist))
            results.append(
                SearchResult(
                    chunk_id=meta.get("chunk_id", ""),
                    article_id=meta.get("article_id", ""),
                    score=score,
                    text=doc or "",
                    model_name=meta.get("model_name", ""),
                    metadata={
                        k: v for k, v in meta.items()
                        if k not in ("chunk_id", "article_id", "model_name")
                    },
                )
            )
        return results

    def delete(self, ids: List[str]) -> int:
        if self._collection is None or not ids:
            return 0
        chroma_ids = [self._stable_id(vid) for vid in ids]
        self._collection.delete(ids=chroma_ids)
        logger.debug("Chroma: حُذف %d vectors", len(ids))
        return len(ids)

    def delete_by_metadata(self, filter_metadata: Dict) -> int:
        if self._collection is None or not filter_metadata:
            return 0
        k, v = next(iter(filter_metadata.items()))
        self._collection.delete(where={k: {"$eq": v}})
        return -1  # ChromaDB لا يُعيد العدد

    # ─── Collection Management ─────────────────────────────────────────────

    def clear(self) -> None:
        if self._client is None:
            return
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Chroma: collection أُفرغت")

    def count(self) -> int:
        return self._collection.count() if self._collection else 0

    def stats(self) -> VectorStoreStats:
        return VectorStoreStats(
            total_vectors=self.count(),
            index_type="chroma:cosine:hnsw",
            dimensions=self.dimensions,
            is_trained=True,
            extra={
                "collection": self.collection_name,
                "persist_dir": self.persist_dir,
            },
        )

    # ─── Persistence ───────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Chroma PersistentClient يحفظ تلقائياً — لا يلزم save صريح."""
        logger.info("Chroma: البيانات محفوظة تلقائياً في '%s'", self.persist_dir)

    def load(self, path: str) -> None:
        """يُعيد الاتصال بنفس persist_dir."""
        self._connect()
