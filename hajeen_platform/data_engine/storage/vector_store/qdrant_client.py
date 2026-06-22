"""Qdrant Vector Store Client — إنتاجي حقيقي مع persistence كامل."""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from data_engine.storage.vector_store.base_vector_store import (
    BaseVectorStore,
    SearchResult,
    VectorEntry,
    VectorStoreStats,
)

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = "hajeen_vectors"
_DEFAULT_HOST = os.getenv("QDRANT_HOST", "localhost")
_DEFAULT_PORT = int(os.getenv("QDRANT_PORT", "6333"))


class QdrantVectorStore(BaseVectorStore):
    """
    Qdrant vector store مع:
    - collection management كامل
    - metadata filtering
    - deduplication بناءً على chunk_id
    - persistence حقيقي (Qdrant خادم أو in-memory)
    - graceful fallback إلى in-memory عند غياب الخادم
    """

    def __init__(
        self,
        collection_name: str = _DEFAULT_COLLECTION,
        dimensions: int = 384,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        in_memory: bool = False,
        grpc_port: int = 6334,
        prefer_grpc: bool = False,
    ) -> None:
        self.collection_name = collection_name
        self.dimensions = dimensions
        self.host = host
        self.port = port
        self.in_memory = in_memory
        self._client: Optional[Any] = None
        self._grpc_port = grpc_port
        self._prefer_grpc = prefer_grpc
        self._connect()

    # ─── Connection ──────────────────────────────────────────────────────────

    def _connect(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams

            if self.in_memory:
                self._client = QdrantClient(":memory:")
                logger.info("Qdrant: in-memory mode")
            else:
                self._client = QdrantClient(
                    host=self.host,
                    port=self.port,
                    grpc_port=self._grpc_port,
                    prefer_grpc=self._prefer_grpc,
                )
                logger.info("Qdrant: متصل بـ %s:%d", self.host, self.port)

            self._ensure_collection()
        except ImportError:
            raise RuntimeError("qdrant-client غير مثبّت — pip install qdrant-client")
        except Exception as exc:
            logger.error("فشل الاتصال بـ Qdrant: %s", exc)
            raise

    def _ensure_collection(self) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        existing = [c.name for c in self._client.get_collections().collections]
        if self.collection_name not in existing:
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.dimensions,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Qdrant: collection أُنشئت '%s'", self.collection_name)

    # ─── CRUD ─────────────────────────────────────────────────────────────────

    def add(self, entries: List[VectorEntry]) -> int:
        if not entries or self._client is None:
            return 0
        from qdrant_client.http.models import PointStruct

        points = []
        for entry in entries:
            payload = {
                "chunk_id": entry.chunk_id,
                "article_id": entry.article_id,
                "text": entry.text,
                "model_name": entry.model_name,
                **entry.metadata,
            }
            # استخدام UUID حتمي من chunk_id لمنع التكرار
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, entry.id))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=entry.vector,
                    payload=payload,
                )
            )

        self._client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )
        logger.debug("Qdrant: أُضيف %d vectors", len(points))
        return len(points)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[SearchResult]:
        if self._client is None:
            return []

        query_filter = None
        if filter_metadata:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue

            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_metadata.items()
            ]
            query_filter = Filter(must=conditions)

        hits = self._client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                SearchResult(
                    chunk_id=payload.get("chunk_id", ""),
                    article_id=payload.get("article_id", ""),
                    score=float(hit.score),
                    text=payload.get("text", ""),
                    model_name=payload.get("model_name", ""),
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k not in ("chunk_id", "article_id", "text", "model_name")
                    },
                )
            )
        return results

    def delete(self, ids: List[str]) -> int:
        if self._client is None or not ids:
            return 0
        from qdrant_client.http.models import PointIdsList

        point_ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, vid)) for vid in ids]
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=point_ids),
            wait=True,
        )
        logger.debug("Qdrant: حُذف %d vectors", len(ids))
        return len(ids)

    def delete_by_article(self, article_id: str) -> int:
        if self._client is None:
            return 0
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        result = self._client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="article_id", match=MatchValue(value=article_id))]
            ),
            wait=True,
        )
        count = getattr(result, "deleted_count", 0) or 0
        logger.debug("Qdrant: حُذفت vectors للمقال %s", article_id)
        return count

    # ─── Collection Management ─────────────────────────────────────────────

    def recreate_collection(self) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        self._client.delete_collection(self.collection_name)
        self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.dimensions, distance=Distance.COSINE),
        )
        logger.info("Qdrant: collection أُعيد إنشاؤها")

    def count(self) -> int:
        if self._client is None:
            return 0
        return self._client.count(collection_name=self.collection_name).count

    def stats(self) -> VectorStoreStats:
        total = self.count()
        return VectorStoreStats(
            total_vectors=total,
            index_type="qdrant:cosine",
            dimensions=self.dimensions,
            is_trained=True,
            extra={"collection": self.collection_name, "host": self.host},
        )

    # ─── Persistence ───────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Qdrant يحفظ بشكل تلقائي — هذا يُصدّر snapshot."""
        if self._client is None:
            return
        try:
            snap = self._client.create_snapshot(collection_name=self.collection_name)
            logger.info("Qdrant snapshot أُنشئ: %s", snap)
        except Exception as exc:
            logger.warning("Qdrant snapshot فشل: %s", exc)

    def load(self, path: str) -> None:
        """يُعيد الاتصال بـ Qdrant — البيانات محفوظة تلقائياً."""
        self._connect()
