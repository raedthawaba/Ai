from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrievalResult:
    __slots__ = ("doc_id", "content", "score", "metadata")

    def __init__(
        self, doc_id: str, content: str, score: float, metadata: Optional[Dict] = None
    ) -> None:
        self.doc_id = doc_id
        self.content = content
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


class SemanticRetriever:
    """Vector-similarity retriever backed by FAISS or any vector store."""

    def __init__(
        self,
        embedding_engine: Any,
        vector_store: Optional[Any] = None,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> None:
        self.embedding_engine = embedding_engine
        self.vector_store = vector_store
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[RetrievalResult]:
        k = top_k or self.top_k
        if self.vector_store is None:
            logger.warning("No vector store configured for retriever")
            return []
        query_vec = self.embedding_engine.embed(query)
        raw = self.vector_store.search(query_vec, top_k=k)
        results = []
        for item in raw:
            score = item.get("score", 0.0)
            if score >= self.score_threshold:
                results.append(
                    RetrievalResult(
                        doc_id=item.get("id", ""),
                        content=item.get("content", ""),
                        score=score,
                        metadata=item.get("metadata", {}),
                    )
                )
        return results

    async def aretrieve(self, query: str, top_k: Optional[int] = None) -> List[RetrievalResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.retrieve, query, top_k)

    def set_vector_store(self, store: Any) -> None:
        self.vector_store = store
        logger.info("Vector store set on SemanticRetriever")
