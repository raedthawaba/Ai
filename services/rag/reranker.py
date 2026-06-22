from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from .retriever import RetrievalResult

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Rerank retrieved docs using a cross-encoder or BM25 scoring."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name
        self._model: Optional[Any] = None
        if model_name:
            self._load(model_name)

    def _load(self, model_name: str) -> None:
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            self._model = CrossEncoder(model_name)
            logger.info("CrossEncoder loaded: %s", model_name)
        except ImportError:
            logger.warning("sentence-transformers not installed; using keyword scorer fallback")

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int] = None,
    ) -> List[RetrievalResult]:
        if not results:
            return []
        if self._model is not None:
            return self._cross_encoder_rerank(query, results, top_k)
        return self._keyword_rerank(query, results, top_k)

    def _cross_encoder_rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int],
    ) -> List[RetrievalResult]:
        pairs = [(query, r.content) for r in results]
        scores = self._model.predict(pairs)  # type: ignore
        for r, score in zip(results, scores):
            r.score = float(score)
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        return sorted_results[:top_k] if top_k else sorted_results

    def _keyword_rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int],
    ) -> List[RetrievalResult]:
        query_tokens = set(query.lower().split())
        for result in results:
            doc_tokens = result.content.lower().split()
            overlap = sum(1 for t in doc_tokens if t in query_tokens)
            idf_boost = math.log(1 + overlap)
            result.score = result.score * 0.7 + idf_boost * 0.3
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        return sorted_results[:top_k] if top_k else sorted_results
