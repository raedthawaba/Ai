"""Vector Retriever — يستخدم Semantic Search Engine."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from services.retrieval.base_retriever import BaseRetriever, RetrievalResult
from services.search.semantic_search import SemanticSearchEngine


class VectorRetriever(BaseRetriever):
    """
    يسترجع الـ chunks عبر Vector Similarity Search.

    Query → SemanticSearchEngine → top-k chunks → RetrievalResult
    """

    def __init__(self, search_engine: SemanticSearchEngine):
        self._engine = search_engine

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict] = None,
    ) -> RetrievalResult:
        t0 = time.perf_counter()
        response = await self._engine.search(
            query=query,
            top_k=top_k,
            filter_metadata=filter_metadata,
        )
        elapsed = (time.perf_counter() - t0) * 1000

        chunks = []
        for hit in response.hits:
            chunks.append({
                "chunk_id": hit.chunk_id,
                "article_id": hit.article_id,
                "text": hit.text,
                "score": hit.score,
                "rank": hit.rank,
                "source_url": hit.source_url,
                "source_title": hit.source_title,
                "metadata": hit.metadata,
            })

        return RetrievalResult(
            query=query,
            chunks=chunks,
            total_retrieved=len(chunks),
            retrieval_time_ms=elapsed,
            retriever_name="VectorRetriever",
            metadata={
                "model_name": response.model_name,
                "index_size": self._engine.index_size(),
            },
        )
