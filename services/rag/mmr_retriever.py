"""MMR Retriever — Maximum Marginal Relevance لتنويع النتائج."""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MMRRetriever:
    """
    Maximum Marginal Relevance Retriever.

    يوازن بين:
    - الصلة بالاستعلام (relevance)
    - التنوع بين النتائج (diversity)

    MMR score = λ × sim(query, doc) - (1-λ) × max_sim(doc, selected)
    """

    def __init__(
        self,
        embedding_fn: Any,
        vector_store: Any,
        lambda_mult: float = 0.5,
        top_k: int = 5,
        fetch_k: int = 20,
    ) -> None:
        self._embed = embedding_fn
        self._store = vector_store
        self.lambda_mult = lambda_mult
        self.top_k = top_k
        self.fetch_k = fetch_k

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict]:
        k = top_k or self.top_k
        fetch_k = max(self.fetch_k, k * 4)

        # 1. Embed query
        query_vec = await self._embed(query)

        # 2. Fetch candidate pool
        candidates = self._store.search(
            query_vector=query_vec,
            top_k=fetch_k,
            filter_metadata=filter_metadata,
        )
        if not candidates:
            return []

        # 3. Extract candidate vectors (if available) or use score as proxy
        candidate_docs = [
            {
                "chunk_id": c.chunk_id,
                "article_id": c.article_id,
                "text": c.text,
                "score": c.score,
                "metadata": c.metadata,
            }
            for c in candidates
        ]

        # 4. MMR selection using scores as similarity proxies
        selected_indices: List[int] = []
        remaining = list(range(len(candidate_docs)))

        for _ in range(min(k, len(candidate_docs))):
            best_idx = -1
            best_score = float("-inf")

            for idx in remaining:
                relevance = candidate_docs[idx]["score"]
                if not selected_indices:
                    mmr = relevance
                else:
                    redundancy = max(
                        self._text_similarity(
                            candidate_docs[idx]["text"],
                            candidate_docs[sel]["text"],
                        )
                        for sel in selected_indices
                    )
                    mmr = self.lambda_mult * relevance - (1 - self.lambda_mult) * redundancy

                if mmr > best_score:
                    best_score = mmr
                    best_idx = idx

            if best_idx == -1:
                break

            selected_indices.append(best_idx)
            remaining.remove(best_idx)
            candidate_docs[best_idx]["mmr_score"] = best_score

        results = [candidate_docs[i] for i in selected_indices]
        logger.debug(
            "MMR: fetched=%d selected=%d lambda=%.2f",
            len(candidates), len(results), self.lambda_mult,
        )
        return results

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Jaccard similarity بين tokens — بديل خفيف عند غياب vectors."""
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
