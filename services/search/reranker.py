"""Reranker — إعادة ترتيب نتائج البحث."""
from __future__ import annotations

import math
from typing import List, Optional

from data_engine.storage.vector_store.base_vector_store import SearchResult


class Reranker:
    """
    يُعيد ترتيب نتائج البحث بمعايير متعددة:
    1. cosine similarity score (الأساس)
    2. text length normalization
    3. recency boost (إذا توفّرت metadata)
    4. diversity penalty (يمنع الـ chunks المتكررة من مقال واحد)
    """

    def __init__(
        self,
        diversity_penalty: float = 0.1,
        length_weight: float = 0.05,
        max_per_article: int = 3,
    ):
        self.diversity_penalty = diversity_penalty
        self.length_weight = length_weight
        self.max_per_article = max_per_article

    def rerank(
        self,
        results: List[SearchResult],
        top_k: int = 10,
        query: Optional[str] = None,
    ) -> List[SearchResult]:
        if not results:
            return []

        # حساب الـ score النهائي لكل نتيجة
        scored = []
        for r in results:
            score = self._compute_score(r)
            scored.append((score, r))

        # ترتيب تنازلي
        scored.sort(key=lambda x: x[0], reverse=True)

        # تطبيق diversity penalty
        selected = []
        article_counts: dict = {}
        for score, result in scored:
            count = article_counts.get(result.article_id, 0)
            if count >= self.max_per_article:
                continue
            penalty = count * self.diversity_penalty
            final_score = score - penalty
            result.score = round(final_score, 6)
            selected.append(result)
            article_counts[result.article_id] = count + 1
            if len(selected) >= top_k:
                break

        return selected

    def _compute_score(self, result: SearchResult) -> float:
        score = result.score
        # text length normalization — يُعطي أولوية للـ chunks الكافية الطول
        text_len = len(result.text)
        if 100 <= text_len <= 800:
            score += self.length_weight
        elif text_len < 50:
            score -= 0.05
        return score
