"""Multi-Query Retriever — يُنشئ صيغاً متعددة ويجمع النتائج."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from services.retrieval.base_retriever import BaseRetriever, RetrievalResult
from services.search.query_processor import QueryProcessor
from services.search.semantic_search import SemanticSearchEngine

logger = logging.getLogger(__name__)


class MultiQueryRetriever(BaseRetriever):
    """
    يُولّد صيغاً متعددة من الاستعلام الأصلي ثم يجمع النتائج ويُزيل التكرار.
    يُحسّن الاسترجاع للاستعلامات الغامضة أو المعقدة.
    """

    def __init__(
        self,
        search_engine: SemanticSearchEngine,
        num_queries: int = 3,
        per_query_k: int = 5,
    ):
        self._engine = search_engine
        self.num_queries = num_queries
        self.per_query_k = per_query_k
        self._query_processor = QueryProcessor()

    def _generate_variants(self, query: str) -> List[str]:
        """توليد صيغ بديلة للاستعلام."""
        processed = self._query_processor.process(query)
        variants = [processed.cleaned]

        # إضافة الصيغ الموسّعة
        variants.extend(processed.expanded[: self.num_queries - 1])

        # توليد صيغة keyword-only
        if processed.keywords:
            keyword_query = " ".join(processed.keywords[:5])
            if keyword_query != processed.cleaned:
                variants.append(keyword_query)

        return list(dict.fromkeys(variants))[: self.num_queries]

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict] = None,
    ) -> RetrievalResult:
        t0 = time.perf_counter()
        variants = self._generate_variants(query)
        logger.debug(f"MultiQuery: {len(variants)} صيغ: {variants}")

        # تنفيذ جميع الاستعلامات بالتوازي
        tasks = [
            self._engine.search(q, top_k=self.per_query_k, filter_metadata=filter_metadata)
            for q in variants
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # جمع النتائج وإزالة التكرار
        seen_chunk_ids = set()
        merged_chunks = []
        for response in responses:
            if isinstance(response, Exception):
                continue
            for hit in response.hits:
                if hit.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(hit.chunk_id)
                    merged_chunks.append({
                        "chunk_id": hit.chunk_id,
                        "article_id": hit.article_id,
                        "text": hit.text,
                        "score": hit.score,
                        "rank": 0,
                        "source_url": hit.source_url,
                        "source_title": hit.source_title,
                        "metadata": hit.metadata,
                    })

        # إعادة الترتيب بالـ score وتعيين الـ rank
        merged_chunks.sort(key=lambda c: c["score"], reverse=True)
        for i, c in enumerate(merged_chunks[:top_k], 1):
            c["rank"] = i

        elapsed = (time.perf_counter() - t0) * 1000
        return RetrievalResult(
            query=query,
            chunks=merged_chunks[:top_k],
            total_retrieved=len(merged_chunks[:top_k]),
            retrieval_time_ms=elapsed,
            retriever_name="MultiQueryRetriever",
            metadata={
                "num_variants": len(variants),
                "total_before_dedup": sum(
                    len(r.hits) for r in responses if not isinstance(r, Exception)
                ),
                "after_dedup": len(merged_chunks),
            },
        )
