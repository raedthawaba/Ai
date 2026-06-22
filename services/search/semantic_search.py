"""Section 7.4 — Semantic Search Engine."""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from data_engine.storage.vector_store.base_vector_store import BaseVectorStore
from services.search.query_processor import QueryProcessor, ProcessedQuery
from services.search.reranker import Reranker
from services.search.search_response import SearchHit, SearchResponse

logger = logging.getLogger(__name__)


class SemanticSearchEngine:
    """
    محرك البحث الدلالي الكامل.

    التدفق:
        query (نص)
          ↓ QueryProcessor
          ↓ EmbeddingManager → query vector
          ↓ VectorStore.search → raw results
          ↓ Reranker → reranked results
          ↓ SearchResponse
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        model_name: Optional[str] = None,
        default_top_k: int = 10,
        rerank: bool = True,
        max_per_article: int = 3,
    ):
        self.vector_store = vector_store
        self.model_name = model_name
        self.default_top_k = default_top_k
        self.rerank = rerank
        self._query_processor = QueryProcessor()
        self._reranker = Reranker(max_per_article=max_per_article)
        self._manager = None

    def _get_manager(self):
        if self._manager is None:
            from core.embeddings.embedding_manager import get_embedding_manager
            self._manager = get_embedding_manager()
        return self._manager

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict] = None,
        search_type: str = "semantic",
    ) -> SearchResponse:
        """بحث دلالي كامل."""
        k = top_k or self.default_top_k
        t0 = time.perf_counter()

        # 1. معالجة الاستعلام
        processed: ProcessedQuery = self._query_processor.process(query)

        # 2. توليد query embedding
        manager = self._get_manager()
        emb = await manager.embed(processed.cleaned, model_name=self.model_name)
        query_vector = emb.vector

        # 3. بحث في Vector Store
        raw_results = self.vector_store.search(
            query_vector=query_vector,
            top_k=k * 3 if self.rerank else k,
            filter_metadata=filter_metadata,
        )

        # 4. إعادة الترتيب
        if self.rerank and raw_results:
            ranked = self._reranker.rerank(raw_results, top_k=k, query=processed.cleaned)
        else:
            ranked = raw_results[:k]

        # 5. بناء الاستجابة
        hits = []
        for i, r in enumerate(ranked, 1):
            hit = SearchHit(
                chunk_id=r.chunk_id,
                article_id=r.article_id,
                text=r.text,
                score=r.score,
                rank=i,
                model_name=r.model_name or emb.model_name,
                metadata=r.metadata,
                source_url=r.metadata.get("url", ""),
                source_title=r.metadata.get("title", ""),
            )
            hits.append(hit)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        response = SearchResponse(
            query=query,
            hits=hits,
            total_found=len(hits),
            search_time_ms=elapsed_ms,
            model_name=emb.model_name,
            query_vector_preview=query_vector[:5],
            search_type=search_type,
            metadata={
                "language": processed.language,
                "is_question": processed.is_question,
                "keywords": processed.keywords,
                "vector_store_size": self.vector_store.stats().total_vectors,
            },
        )

        logger.info(
            f"بحث: '{query[:50]}' → {len(hits)} نتيجة في {elapsed_ms:.1f}ms"
        )
        return response

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        semantic_weight: float = 0.7,
        filter_metadata: Optional[Dict] = None,
    ) -> SearchResponse:
        """بحث هجين: semantic + keyword (أساس للـ Phase 8)."""
        semantic_response = await self.search(
            query, top_k=top_k * 2, filter_metadata=filter_metadata,
            search_type="hybrid",
        )
        processed = self._query_processor.process(query)

        # keyword boosting بسيط — يرفع نتائج تحتوي الكلمات المفتاحية
        boosted = []
        keywords_lower = [kw.lower() for kw in processed.keywords]
        for hit in semantic_response.hits:
            text_lower = hit.text.lower()
            keyword_matches = sum(1 for kw in keywords_lower if kw in text_lower)
            keyword_boost = keyword_matches * 0.02
            hit.score = round(
                semantic_weight * hit.score + (1 - semantic_weight) * keyword_boost, 6
            )
            boosted.append(hit)

        boosted.sort(key=lambda h: h.score, reverse=True)
        for i, h in enumerate(boosted[:top_k], 1):
            h.rank = i

        semantic_response.hits = boosted[:top_k]
        semantic_response.total_found = len(semantic_response.hits)
        semantic_response.search_type = "hybrid"
        return semantic_response

    def index_size(self) -> int:
        return self.vector_store.stats().total_vectors
