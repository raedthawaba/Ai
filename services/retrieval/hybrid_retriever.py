"""Hybrid Retriever — يجمع vector search + keyword matching."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from services.retrieval.base_retriever import BaseRetriever, RetrievalResult
from services.search.semantic_search import SemanticSearchEngine


class HybridRetriever(BaseRetriever):
    """
    يجمع بين:
    1. Vector Search (semantic similarity)
    2. Keyword Boost (exact/partial match)

    يُعطي نتائج أفضل للاستعلامات التي تحتوي كلمات مفتاحية محددة.
    """

    def __init__(
        self,
        search_engine: SemanticSearchEngine,
        semantic_weight: float = 0.7,
    ):
        self._engine = search_engine
        self.semantic_weight = semantic_weight

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict] = None,
    ) -> RetrievalResult:
        t0 = time.perf_counter()
        response = await self._engine.hybrid_search(
            query=query,
            top_k=top_k,
            semantic_weight=self.semantic_weight,
            filter_metadata=filter_metadata,
        )
        elapsed = (time.perf_counter() - t0) * 1000

        chunks = [
            {
                "chunk_id": h.chunk_id,
                "article_id": h.article_id,
                "text": h.text,
                "score": h.score,
                "rank": h.rank,
                "source_url": h.source_url,
                "source_title": h.source_title,
                "metadata": h.metadata,
            }
            for h in response.hits
        ]

        return RetrievalResult(
            query=query,
            chunks=chunks,
            total_retrieved=len(chunks),
            retrieval_time_ms=elapsed,
            retriever_name="HybridRetriever",
            metadata={
                "semantic_weight": self.semantic_weight,
                "keyword_weight": round(1 - self.semantic_weight, 2),
            },
        )
