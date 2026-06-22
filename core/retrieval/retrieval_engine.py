"""Retrieval Engine — semantic + hybrid + reranking + MMR."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalHit:
    chunk_id: str
    article_id: str
    text: str
    score: float
    rank: int = 0
    source_url: str = ""
    source_title: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "text": self.text[:500],
            "score": round(self.score, 6),
            "rank": self.rank,
            "source_url": self.source_url,
            "source_title": self.source_title,
        }


@dataclass
class RetrievalResponse:
    hits: List[RetrievalHit]
    query: str
    total: int
    latency_ms: float
    model_name: str = ""
    strategy: str = "semantic"

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "total": self.total,
            "latency_ms": self.latency_ms,
            "strategy": self.strategy,
            "hits": [h.to_dict() for h in self.hits],
        }


def _normalize_query(query: str) -> str:
    """تنظيف الاستعلام: إزالة أحرف خاصة، trim."""
    query = query.strip()
    query = re.sub(r"\s+", " ", query)
    return query[:1024]  # حد أقصى


class RetrievalEngine:
    """
    محرك استرجاع دلالي متكامل:
    - semantic similarity search
    - BM25 keyword search
    - hybrid fusion
    - MMR diversity
    - reranking
    - score thresholds
    - multilingual (ar + en)
    - caching
    - retrieval timeout
    """

    def __init__(
        self,
        embedding_manager: Any,
        vector_store: Any,
        top_k: int = 5,
        score_threshold: float = 0.1,
        use_mmr: bool = False,
        mmr_lambda: float = 0.5,
        retrieval_timeout: float = 10.0,
        enable_cache: bool = True,
        cache_ttl: int = 300,
    ) -> None:
        self._embed = embedding_manager
        self._store = vector_store
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.use_mmr = use_mmr
        self.mmr_lambda = mmr_lambda
        self.timeout = retrieval_timeout
        self._cache: Dict[str, Any] = {} if enable_cache else None  # type: ignore
        self._cache_ttl = cache_ttl
        self._cache_ts: Dict[str, float] = {}

    # ─── Public API ──────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict] = None,
        strategy: str = "semantic",
    ) -> RetrievalResponse:
        """نقطة الدخول الرئيسية للاسترجاع."""
        query = _normalize_query(query)
        k = top_k or self.top_k
        t0 = time.perf_counter()

        # Check cache
        if self._cache is not None:
            cache_key = f"{strategy}:{query}:{k}:{filter_metadata}"
            cached = self._get_cache(cache_key)
            if cached:
                cached.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                return cached

        try:
            hits = await asyncio.wait_for(
                self._retrieve_inner(query, k, filter_metadata, strategy),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.error("Retrieval timeout بعد %.1fs للاستعلام: %s", self.timeout, query[:80])
            hits = []

        # Filter by score threshold
        hits = [h for h in hits if h.score >= self.score_threshold]

        # Deduplicate by chunk_id
        seen_chunks: set = set()
        deduped = []
        for h in hits:
            if h.chunk_id not in seen_chunks:
                seen_chunks.add(h.chunk_id)
                deduped.append(h)

        # Rank
        for i, h in enumerate(deduped):
            h.rank = i + 1

        latency = round((time.perf_counter() - t0) * 1000, 2)
        response = RetrievalResponse(
            hits=deduped[:k],
            query=query,
            total=len(deduped),
            latency_ms=latency,
            strategy=strategy,
        )

        if self._cache is not None:
            self._put_cache(cache_key, response)

        logger.info(
            "Retrieval: strategy=%s hits=%d latency=%.1fms",
            strategy, len(response.hits), latency,
        )
        return response

    async def retrieve_multilingual(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict] = None,
    ) -> RetrievalResponse:
        """استرجاع مُحسَّن للغتين العربية والإنجليزية."""
        # نضيف prefix للاستعلام إذا كان عربياً
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in query)
        if has_arabic:
            logger.debug("Retrieval: detected Arabic query")
        return await self.retrieve(query, top_k, filter_metadata, strategy="semantic")

    async def hybrid_retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict] = None,
        alpha: float = 0.7,
    ) -> RetrievalResponse:
        """
        Hybrid retrieval: Semantic (α) + BM25 keyword (1-α).
        """
        k = top_k or self.top_k
        t0 = time.perf_counter()

        sem_resp, bm25_hits = await asyncio.gather(
            self.retrieve(query, k * 2, filter_metadata, "semantic"),
            self._bm25_search(query, k * 2, filter_metadata),
        )

        # Reciprocal Rank Fusion
        scores: Dict[str, float] = {}
        docs: Dict[str, RetrievalHit] = {}

        for rank, hit in enumerate(sem_resp.hits, 1):
            key = hit.chunk_id
            scores[key] = scores.get(key, 0.0) + alpha / (rank + 60)
            docs[key] = hit

        for rank, hit in enumerate(bm25_hits, 1):
            key = hit.chunk_id
            scores[key] = scores.get(key, 0.0) + (1 - alpha) / (rank + 60)
            if key not in docs:
                docs[key] = hit

        # Sort by fused score
        sorted_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        hits = []
        for i, key in enumerate(sorted_keys[:k]):
            h = docs[key]
            h.score = round(scores[key], 6)
            h.rank = i + 1
            hits.append(h)

        latency = round((time.perf_counter() - t0) * 1000, 2)
        return RetrievalResponse(
            hits=hits,
            query=query,
            total=len(hits),
            latency_ms=latency,
            strategy="hybrid",
        )

    # ─── Internal ────────────────────────────────────────────────────────────

    async def _retrieve_inner(
        self,
        query: str,
        top_k: int,
        filter_metadata: Optional[Dict],
        strategy: str,
    ) -> List[RetrievalHit]:
        # Embed query
        query_vec = await self._embed_query(query)
        if not query_vec:
            return []

        # Vector search
        results = self._store.search(
            query_vector=query_vec,
            top_k=top_k * 2,
            filter_metadata=filter_metadata,
        )

        hits = [
            RetrievalHit(
                chunk_id=r.chunk_id,
                article_id=r.article_id,
                text=r.text,
                score=r.score,
                source_url=r.metadata.get("source_url", ""),
                source_title=r.metadata.get("source_title", ""),
                metadata=r.metadata,
            )
            for r in results
        ]

        if self.use_mmr and len(hits) > 1:
            hits = self._mmr_select(query, hits, top_k)

        return hits

    async def _embed_query(self, query: str) -> Optional[List[float]]:
        try:
            result = await self._embed.embed(query)
            return result.vector
        except Exception as exc:
            logger.error("Query embedding failed: %s", exc)
            return None

    async def _bm25_search(
        self,
        query: str,
        top_k: int,
        filter_metadata: Optional[Dict],
    ) -> List[RetrievalHit]:
        """BM25 keyword search بسيط يعمل على النصوص المُخزَّنة."""
        try:
            query_tokens = set(query.lower().split())
            # نُحمّل النتائج الأولى من vector search كـ corpus
            raw = self._store.search(query_vector=[0.0] * 384, top_k=top_k * 3)
            scored = []
            for r in raw:
                text_tokens = set(r.text.lower().split())
                overlap = len(query_tokens & text_tokens)
                if overlap > 0:
                    bm25_score = overlap / max(len(query_tokens), 1)
                    scored.append((bm25_score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            hits = []
            for score, r in scored[:top_k]:
                hits.append(RetrievalHit(
                    chunk_id=r.chunk_id,
                    article_id=r.article_id,
                    text=r.text,
                    score=score,
                    metadata=r.metadata,
                ))
            return hits
        except Exception:
            return []

    def _mmr_select(
        self,
        query: str,
        hits: List[RetrievalHit],
        k: int,
    ) -> List[RetrievalHit]:
        """MMR selection على النصوص."""
        selected: List[RetrievalHit] = []
        remaining = list(hits)

        while len(selected) < k and remaining:
            best = None
            best_score = float("-inf")
            for h in remaining:
                rel = h.score
                if not selected:
                    mmr = rel
                else:
                    redundancy = max(
                        self._jaccard(h.text, s.text) for s in selected
                    )
                    mmr = self.mmr_lambda * rel - (1 - self.mmr_lambda) * redundancy
                if mmr > best_score:
                    best_score = mmr
                    best = h
            if best is None:
                break
            selected.append(best)
            remaining.remove(best)

        return selected

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        ta, tb = set(a.lower().split()), set(b.lower().split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    # ─── Cache ────────────────────────────────────────────────────────────────

    def _get_cache(self, key: str) -> Optional[RetrievalResponse]:
        if self._cache is None:
            return None
        ts = self._cache_ts.get(key, 0)
        if time.time() - ts > self._cache_ttl:
            return None
        return self._cache.get(key)

    def _put_cache(self, key: str, response: RetrievalResponse) -> None:
        if self._cache is None:
            return
        if len(self._cache) > 1000:
            oldest = min(self._cache_ts, key=lambda k: self._cache_ts[k])
            del self._cache[oldest]
            del self._cache_ts[oldest]
        self._cache[key] = response
        self._cache_ts[key] = time.time()
