"""Retrieval Evaluator — تقييم جودة الاسترجاع."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class EvalResult:
    """نتيجة تقييم عملية استرجاع."""
    query: str
    retrieved_ids: List[str]
    relevant_ids: Optional[List[str]] = None
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    ndcg: float = 0.0
    mrr: float = 0.0
    hit_at_k: bool = False
    duplicate_rate: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query[:100],
            "retrieved": len(self.retrieved_ids),
            "precision@k": round(self.precision_at_k, 4),
            "recall@k": round(self.recall_at_k, 4),
            "ndcg": round(self.ndcg, 4),
            "mrr": round(self.mrr, 4),
            "hit@k": self.hit_at_k,
            "duplicate_rate": round(self.duplicate_rate, 4),
        }


class RetrievalEvaluator:
    """
    يُقيّم جودة الاسترجاع بمقاييس متعددة.
    يعمل بدون ground-truth (unsupervised) أو معه (supervised).
    """

    def evaluate(
        self,
        query: str,
        retrieved_ids: List[str],
        relevant_ids: Optional[List[str]] = None,
        scores: Optional[List[float]] = None,
        k: int = 10,
    ) -> EvalResult:
        retrieved = retrieved_ids[:k]
        rel_set: Set[str] = set(relevant_ids) if relevant_ids else set()

        precision = self._precision(retrieved, rel_set)
        recall = self._recall(retrieved, rel_set)
        ndcg = self._ndcg(retrieved, rel_set, scores, k)
        mrr = self._mrr(retrieved, rel_set)
        hit = any(rid in rel_set for rid in retrieved) if rel_set else bool(retrieved)
        dup_rate = self._duplicate_rate(retrieved)

        return EvalResult(
            query=query,
            retrieved_ids=retrieved,
            relevant_ids=relevant_ids,
            precision_at_k=precision,
            recall_at_k=recall,
            ndcg=ndcg,
            mrr=mrr,
            hit_at_k=hit,
            duplicate_rate=dup_rate,
        )

    def _precision(self, retrieved: List[str], relevant: Set[str]) -> float:
        if not retrieved or not relevant:
            return 0.0
        return len(set(retrieved) & relevant) / len(retrieved)

    def _recall(self, retrieved: List[str], relevant: Set[str]) -> float:
        if not relevant:
            return 1.0
        return len(set(retrieved) & relevant) / len(relevant)

    def _ndcg(
        self,
        retrieved: List[str],
        relevant: Set[str],
        scores: Optional[List[float]],
        k: int,
    ) -> float:
        import math
        if not relevant:
            return 1.0 if retrieved else 0.0
        dcg = sum(
            (1.0 if rid in relevant else 0.0) / math.log2(i + 2)
            for i, rid in enumerate(retrieved[:k])
        )
        ideal = sum(
            1.0 / math.log2(i + 2)
            for i in range(min(len(relevant), k))
        )
        return dcg / ideal if ideal > 0 else 0.0

    def _mrr(self, retrieved: List[str], relevant: Set[str]) -> float:
        if not relevant:
            return 0.0
        for i, rid in enumerate(retrieved, 1):
            if rid in relevant:
                return 1.0 / i
        return 0.0

    def _duplicate_rate(self, retrieved: List[str]) -> float:
        if not retrieved:
            return 0.0
        return 1.0 - (len(set(retrieved)) / len(retrieved))

    def batch_evaluate(
        self,
        queries_results: List[Dict],
    ) -> Dict:
        """تقييم مجموعة استعلامات ويُعيد متوسطات."""
        all_results = [
            self.evaluate(
                query=qr["query"],
                retrieved_ids=qr["retrieved_ids"],
                relevant_ids=qr.get("relevant_ids"),
                scores=qr.get("scores"),
            )
            for qr in queries_results
        ]
        if not all_results:
            return {}
        return {
            "num_queries": len(all_results),
            "mean_precision@k": round(sum(r.precision_at_k for r in all_results) / len(all_results), 4),
            "mean_recall@k": round(sum(r.recall_at_k for r in all_results) / len(all_results), 4),
            "mean_ndcg": round(sum(r.ndcg for r in all_results) / len(all_results), 4),
            "mean_mrr": round(sum(r.mrr for r in all_results) / len(all_results), 4),
            "hit_rate": round(sum(1 for r in all_results if r.hit_at_k) / len(all_results), 4),
            "mean_duplicate_rate": round(sum(r.duplicate_rate for r in all_results) / len(all_results), 4),
        }
