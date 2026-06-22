from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from .retriever import RetrievalResult, SemanticRetriever

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Combines semantic (dense) and keyword (sparse) retrieval with RRF fusion."""

    def __init__(
        self,
        semantic_retriever: SemanticRetriever,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7,
        rrf_k: int = 60,
    ) -> None:
        self.semantic_retriever = semantic_retriever
        self.keyword_weight = keyword_weight
        self.semantic_weight = semantic_weight
        self.rrf_k = rrf_k

    def search(
        self, query: str, top_k: int = 10, corpus: Optional[List[Dict]] = None
    ) -> List[RetrievalResult]:
        semantic_results = self.semantic_retriever.retrieve(query, top_k=top_k * 2)
        keyword_results = self._keyword_search(query, corpus or [], top_k=top_k * 2)
        fused = self._rrf_fusion(semantic_results, keyword_results, top_k=top_k)
        return fused

    def _keyword_search(
        self, query: str, corpus: List[Dict], top_k: int
    ) -> List[RetrievalResult]:
        query_tokens = set(query.lower().split())
        scored: List[tuple] = []
        for doc in corpus:
            content = doc.get("content", doc.get("text", ""))
            doc_tokens = content.lower().split()
            if not doc_tokens:
                continue
            tf: Dict[str, float] = {}
            for t in doc_tokens:
                tf[t] = tf.get(t, 0) + 1
            score = sum(tf.get(t, 0) / len(doc_tokens) for t in query_tokens)
            if score > 0:
                scored.append((doc, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            RetrievalResult(
                doc_id=doc.get("id", ""),
                content=doc.get("content", doc.get("text", "")),
                score=score,
                metadata=doc.get("metadata", {}),
            )
            for doc, score in scored[:top_k]
        ]

    def _rrf_fusion(
        self,
        semantic: List[RetrievalResult],
        keyword: List[RetrievalResult],
        top_k: int,
    ) -> List[RetrievalResult]:
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, RetrievalResult] = {}

        for rank, result in enumerate(semantic):
            key = result.doc_id or result.content[:50]
            rrf_scores[key] = rrf_scores.get(key, 0) + self.semantic_weight / (self.rrf_k + rank + 1)
            doc_map[key] = result

        for rank, result in enumerate(keyword):
            key = result.doc_id or result.content[:50]
            rrf_scores[key] = rrf_scores.get(key, 0) + self.keyword_weight / (self.rrf_k + rank + 1)
            if key not in doc_map:
                doc_map[key] = result

        sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)
        results: List[RetrievalResult] = []
        for key in sorted_keys[:top_k]:
            r = doc_map[key]
            r.score = rrf_scores[key]
            results.append(r)
        return results
