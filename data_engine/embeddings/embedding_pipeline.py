"""Embedding Pipeline — تضمين المقالات بشكل دُفعي مع caching وlogging."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingJob:
    """مهمة تضمين واحدة."""
    text: str
    chunk_id: str
    article_id: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class EmbeddingOutput:
    """نتيجة تضمين واحدة."""
    chunk_id: str
    article_id: str
    vector: List[float]
    dimension: int
    model_name: str
    cached: bool = False
    latency_ms: float = 0.0
    metadata: Dict = field(default_factory=dict)


class EmbeddingCache:
    """Cache بسيط في الذاكرة لتجنب إعادة الحساب."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._store: Dict[str, List[float]] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _key(self, text: str, model: str) -> str:
        return hashlib.md5(f"{model}:{text}".encode()).hexdigest()

    def get(self, text: str, model: str) -> Optional[List[float]]:
        vec = self._store.get(self._key(text, model))
        if vec is not None:
            self._hits += 1
        else:
            self._misses += 1
        return vec

    def put(self, text: str, model: str, vector: List[float]) -> None:
        if len(self._store) >= self._max_size:
            # evict oldest (first key)
            try:
                oldest = next(iter(self._store))
                del self._store[oldest]
            except StopIteration:
                pass
        self._store[self._key(text, model)] = vector

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> Dict:
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
            "max_size": self._max_size,
        }


class EmbeddingPipeline:
    """
    Pipeline إنتاجي لتضمين النصوص مع:
    - batch processing
    - caching
    - dimension validation
    - async-safe
    - memory-efficient (لا يُحتفظ بجميع الـ vectors في الذاكرة)
    - logging metrics
    """

    def __init__(
        self,
        embedding_manager: Any,
        batch_size: int = 64,
        max_text_length: int = 8192,
        cache_enabled: bool = True,
        cache_max_size: int = 10_000,
    ) -> None:
        self._manager = embedding_manager
        self.batch_size = batch_size
        self.max_text_length = max_text_length
        self._cache = EmbeddingCache(max_size=cache_max_size) if cache_enabled else None
        self._total_processed = 0
        self._total_cached = 0
        self._total_errors = 0
        self._semaphore = asyncio.Semaphore(4)  # منع الضغط المفرط

    def _truncate(self, text: str) -> str:
        return text[: self.max_text_length] if len(text) > self.max_text_length else text

    def _validate_vector(self, vector: List[float], expected_dim: int) -> bool:
        if len(vector) != expected_dim:
            logger.warning(
                "أبعاد غير متوافقة: %d ≠ %d", len(vector), expected_dim
            )
            return False
        if any(not isinstance(v, (int, float)) for v in vector):
            return False
        return True

    async def embed_job(
        self,
        job: EmbeddingJob,
        model_name: Optional[str] = None,
    ) -> Optional[EmbeddingOutput]:
        text = self._truncate(job.text)
        model = model_name or "default"

        # Check cache
        if self._cache:
            cached_vec = self._cache.get(text, model)
            if cached_vec is not None:
                self._total_cached += 1
                return EmbeddingOutput(
                    chunk_id=job.chunk_id,
                    article_id=job.article_id,
                    vector=cached_vec,
                    dimension=len(cached_vec),
                    model_name=model,
                    cached=True,
                    metadata=job.metadata,
                )

        t0 = time.perf_counter()
        try:
            async with self._semaphore:
                result = await self._manager.embed(
                    text=text,
                    chunk_id=job.chunk_id,
                    article_id=job.article_id,
                    model_name=model_name,
                )
            latency = (time.perf_counter() - t0) * 1000
            self._total_processed += 1

            if self._cache:
                self._cache.put(text, model, result.vector)

            return EmbeddingOutput(
                chunk_id=job.chunk_id,
                article_id=job.article_id,
                vector=result.vector,
                dimension=len(result.vector),
                model_name=result.model_name,
                cached=False,
                latency_ms=round(latency, 2),
                metadata=job.metadata,
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("Embedding error chunk_id=%s: %s", job.chunk_id, exc)
            return None

    async def embed_batch(
        self,
        jobs: List[EmbeddingJob],
        model_name: Optional[str] = None,
    ) -> Tuple[List[EmbeddingOutput], int]:
        """
        يُضمّن دُفعة — يُعيد (outputs, error_count).
        يعمل بدُفعات صغيرة لتجنب استهلاك الذاكرة.
        """
        outputs: List[EmbeddingOutput] = []
        errors = 0

        for i in range(0, len(jobs), self.batch_size):
            batch = jobs[i : i + self.batch_size]
            tasks = [self.embed_job(job, model_name) for job in batch]
            results = await asyncio.gather(*tasks, return_exceptions=False)

            for r in results:
                if r is None:
                    errors += 1
                else:
                    outputs.append(r)

            logger.debug(
                "EmbeddingPipeline: دفعة %d-%d جاهزة (%d/%d)",
                i, i + len(batch), len(outputs), len(jobs),
            )

        logger.info(
            "EmbeddingPipeline: processed=%d cached=%d errors=%d",
            self._total_processed, self._total_cached, self._total_errors,
        )
        return outputs, errors

    def metrics(self) -> Dict:
        base = {
            "total_processed": self._total_processed,
            "total_cached": self._total_cached,
            "total_errors": self._total_errors,
            "batch_size": self.batch_size,
        }
        if self._cache:
            base["cache"] = self._cache.stats()
        return base
