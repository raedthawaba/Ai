"""Embedding Task Pipeline — Phase 6.5.

Pipeline لحساب وتخزين الـ embeddings بشكل دُفعات.

التدفق:
  DocumentChunks → Dedup → Cache Check → Embed → Store → Update Article
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base_embedder import BaseEmbedder, EmbeddingRequest, EmbeddingResult, create_embedder
from .embedding_cache import EmbeddingCache
from .embedding_storage import EmbeddingRecord, EmbeddingStorage
from .embedding_metadata import EmbeddingMetadataTracker

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmbeddingPipelineResult:
    """نتيجة تشغيل Embedding Pipeline."""

    run_id: str
    total_requested: int = 0
    total_computed: int = 0
    total_cached: int = 0
    total_stored: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    duration_ms: float = 0.0
    model_name: str = ""
    embedding_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def cache_hit_rate(self) -> float:
        total = self.total_computed + self.total_cached
        return self.total_cached / total if total > 0 else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total_requested": self.total_requested,
            "total_computed": self.total_computed,
            "total_cached": self.total_cached,
            "total_stored": self.total_stored,
            "total_errors": self.total_errors,
            "cache_hit_rate": round(self.cache_hit_rate, 3),
            "duration_ms": round(self.duration_ms, 2),
            "model": self.model_name,
        }


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingPipeline
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingPipeline:
    """Pipeline احترافي لحساب وتخزين الـ embeddings.

    Parameters
    ----------
    embedder:
        مولّد الـ embeddings (BaseEmbedder).
    cache:
        طبقة الـ cache (EmbeddingCache).
    storage:
        مخزن الـ embeddings (EmbeddingStorage).
    tracker:
        متتبع البيانات الوصفية (EmbeddingMetadataTracker).
    batch_size:
        حجم الدُفعة لإرسال الطلبات للـ API.
    """

    def __init__(
        self,
        embedder: Optional[BaseEmbedder] = None,
        cache: Optional[EmbeddingCache] = None,
        storage: Optional[EmbeddingStorage] = None,
        tracker: Optional[EmbeddingMetadataTracker] = None,
        batch_size: int = 32,
    ) -> None:
        self.embedder = embedder or create_embedder("mock")
        self.cache = cache or EmbeddingCache()
        self.storage = storage or EmbeddingStorage()
        self.tracker = tracker or EmbeddingMetadataTracker()
        self.batch_size = batch_size

    async def process_chunks(
        self,
        chunks: List[Any],
        article_id: Optional[str] = None,
        language: str = "en",
    ) -> EmbeddingPipelineResult:
        """حساب embeddings لدُفعة من DocumentChunks.

        Parameters
        ----------
        chunks:
            قائمة DocumentChunk.
        article_id:
            معرّف المقال المصدر.
        language:
            لغة المحتوى.

        Returns
        -------
        EmbeddingPipelineResult
        """
        from data_engine.processing.transformation.chunking_engine import DocumentChunk

        run_id = str(uuid.uuid4())[:8]
        t_start = time.time()

        result = EmbeddingPipelineResult(
            run_id=run_id,
            total_requested=len(chunks),
            model_name=self.embedder.model_name,
        )

        if not chunks:
            return result

        # ── 1. Cache Check ────────────────────────────────────────────────────
        to_compute: List[Tuple[Any, EmbeddingRequest]] = []
        cached_ids: List[str] = []

        for chunk in chunks:
            if isinstance(chunk, DocumentChunk):
                chunk_id = chunk.chunk_id
                text = chunk.text
                order = chunk.order
            elif isinstance(chunk, dict):
                chunk_id = str(chunk.get("chunk_id", ""))
                text = str(chunk.get("text", ""))
                order = int(chunk.get("order", 0))
            else:
                continue

            # فحص الـ cache
            cached_vector = self.cache.get(text, self.embedder.model_name)
            if cached_vector is not None:
                # تخزين من الـ cache
                emb_record = EmbeddingRecord(
                    embedding_id="emb_" + chunk_id[:16],
                    source_id=chunk_id,
                    source_type="chunk",
                    article_id=article_id,
                    chunk_order=order,
                    model_name=self.embedder.model_name,
                    provider=self.embedder.provider,
                    dimensions=len(cached_vector),
                    vector=cached_vector,
                    text_preview=text[:200],
                    language=language,
                )
                self.storage.save(emb_record)
                result.embedding_ids.append(emb_record.embedding_id)
                cached_ids.append(chunk_id)
            else:
                req = EmbeddingRequest(
                    request_id=str(uuid.uuid4())[:8],
                    text=text,
                    source_id=chunk_id,
                    source_type="chunk",
                    metadata={"article_id": article_id, "order": order},
                )
                to_compute.append((chunk, req))

        result.total_cached = len(cached_ids)

        # ── 2. Batch Embedding ────────────────────────────────────────────────
        if to_compute:
            for batch_start in range(0, len(to_compute), self.batch_size):
                batch = to_compute[batch_start: batch_start + self.batch_size]
                requests = [req for _, req in batch]

                try:
                    emb_results: List[EmbeddingResult] = await self.embedder.embed_batch(
                        requests
                    )
                except Exception as exc:
                    logger.error("EmbeddingPipeline: خطأ في الـ batch — %s", exc)
                    result.total_errors += len(batch)
                    result.errors.append(str(exc))
                    continue

                # ── 3. Store ──────────────────────────────────────────────────
                for (chunk, req), emb_res in zip(batch, emb_results):
                    if emb_res.error:
                        result.total_errors += 1
                        result.errors.append(emb_res.error)
                        continue

                    # تخزين في الـ cache
                    self.cache.set(
                        req.text,
                        self.embedder.model_name,
                        emb_res.vector,
                        source_id=req.source_id,
                        token_count=emb_res.token_count,
                    )

                    # استخراج chunk_order
                    from data_engine.processing.transformation.chunking_engine import DocumentChunk
                    if isinstance(chunk, DocumentChunk):
                        order = chunk.order
                    else:
                        order = int(chunk.get("order", 0)) if isinstance(chunk, dict) else 0

                    # تخزين في storage
                    emb_record = EmbeddingRecord(
                        embedding_id=emb_res.embedding_id,
                        source_id=req.source_id,
                        source_type="chunk",
                        article_id=article_id,
                        chunk_order=order,
                        model_name=emb_res.model_name,
                        provider=emb_res.provider,
                        dimensions=emb_res.dimensions,
                        vector=emb_res.vector,
                        token_count=emb_res.token_count,
                        text_preview=req.text[:200],
                        language=language,
                        processing_ms=emb_res.processing_ms,
                    )
                    self.storage.save(emb_record)
                    result.embedding_ids.append(emb_record.embedding_id)
                    result.total_computed += 1

        result.total_stored = len(result.embedding_ids)
        result.duration_ms = (time.time() - t_start) * 1000

        # ── 4. تسجيل في الـ tracker ───────────────────────────────────────────
        self.tracker.record_pipeline_run(
            run_id=run_id,
            article_id=article_id or "",
            chunk_count=len(chunks),
            embedding_count=result.total_stored,
            model_name=self.embedder.model_name,
            duration_ms=result.duration_ms,
        )

        logger.info(
            "EmbeddingPipeline: run=%s chunks=%d computed=%d cached=%d errors=%d",
            run_id, len(chunks), result.total_computed,
            result.total_cached, result.total_errors,
        )
        return result

    async def process_article(
        self,
        article: Any,
        chunking_config: Optional[Any] = None,
        language: str = "en",
    ) -> EmbeddingPipelineResult:
        """معالجة مقال كامل: chunking → embedding.

        Parameters
        ----------
        article:
            UnifiedArticle أو Article.
        chunking_config:
            ChunkingConfig اختياري.
        language:
            لغة المحتوى.
        """
        from data_engine.processing.transformation.chunking_engine import (
            ChunkingEngine, ChunkingConfig
        )
        from shared.schemas.unified_article import UnifiedArticle
        from shared.schemas.article import Article

        if isinstance(article, UnifiedArticle):
            article_id = article.id
            language = article.language
        elif isinstance(article, Article):
            article_id = article.id
            language = article.metadata.language
        else:
            article_id = str(getattr(article, "id", "unknown"))

        engine = ChunkingEngine(config=chunking_config or ChunkingConfig())
        chunks = engine.chunk_article(article)

        if not chunks:
            logger.warning(
                "EmbeddingPipeline: لا توجد chunks للمقال %s", article_id
            )
            return EmbeddingPipelineResult(
                run_id=str(uuid.uuid4())[:8],
                total_requested=0,
                model_name=self.embedder.model_name,
            )

        return await self.process_chunks(
            chunks=chunks,
            article_id=article_id,
            language=language,
        )

    async def health_check(self) -> Dict[str, Any]:
        """فحص صحة جميع مكونات الـ pipeline."""
        embedder_health = await self.embedder.health_check()
        return {
            "embedder": embedder_health,
            "cache": self.cache.stats(),
            "storage": self.storage.stats(),
            "batch_size": self.batch_size,
        }
