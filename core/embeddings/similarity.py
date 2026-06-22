from __future__ import annotations

import math
from typing import List, Tuple


class SimilarityScorer:
    """Vector similarity calculations."""

    @staticmethod
    def cosine(vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def euclidean(vec_a: List[float], vec_b: List[float]) -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))

    @staticmethod
    def dot_product(vec_a: List[float], vec_b: List[float]) -> float:
        return sum(a * b for a, b in zip(vec_a, vec_b))

    @staticmethod
    def normalize(vec: List[float]) -> List[float]:
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]

    @classmethod
    def rank_by_similarity(
        cls,
        query_vec: List[float],
        candidates: List[Tuple[str, List[float]]],
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        scored = [(doc_id, cls.cosine(query_vec, vec)) for doc_id, vec in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @classmethod
    def find_similar(
        cls,
        query_vec: List[float],
        corpus_vecs: List[List[float]],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> List[Tuple[int, float]]:
        scored = [(i, cls.cosine(query_vec, vec)) for i, vec in enumerate(corpus_vecs)]
        scored = [(i, s) for i, s in scored if s >= threshold]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
