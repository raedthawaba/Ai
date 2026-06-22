"""Section 7.2 — Chunk Embedding Pipeline Stage."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChunkEmbeddingRecord:
    """سجل embedding كامل لـ chunk واحد."""
    chunk_id: str
    article_id: str
    text: str
    vector: List[float]
    model_name: str
    embedding_dim: int
    created_at: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    token_count: int = 0
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "latency_ms": round(self.latency_ms, 3),
            "token_count": self.token_count,
            "vector_preview": self.vector[:4],
        }


@dataclass
class EmbedStageResult:
    """نتيجة مرحلة الـ embedding الكاملة."""
    article_id: str
    total_chunks: int
    embedded: int
    failed: int
    records: List[ChunkEmbeddingRecord] = field(default_factory=list)
    total_ms: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return self.embedded / self.total_chunks

    def to_dict(self) -> dict:
        return {
            "article_id": self.article_id,
            "total_chunks": self.total_chunks,
            "embedded": self.embedded,
            "failed": self.failed,
            "success_rate": round(self.success_rate, 3),
            "total_ms": round(self.total_ms, 2),
            "errors": self.errors,
        }


class ChunkEmbeddingStage:
    """
    مرحلة توليد الـ embeddings للـ chunks.

    التدفق:
        Article
          ↓ chunking (يُفترض أنه تمّ مسبقاً)
          ↓ ChunkEmbeddingStage.process(chunks)
          ↓ EmbedStageResult (records مع vectors)
    """

    def __init__(
        self,
        batch_size: int = 32,
        max_retries: int = 3,
        retry_delay_s: float = 0.5,
        model_name: Optional[str] = None,
    ):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay_s = retry_delay_s
        self.model_name = model_name
        self._manager = None

    def _get_manager(self):
        if self._manager is None:
            from core.embeddings.embedding_manager import get_embedding_manager
            self._manager = get_embedding_manager()
        return self._manager

    async def _embed_with_retry(
        self,
        texts: List[str],
        chunk_ids: List[str],
        article_id: str,
    ):
        """تضمين دُفعة مع إعادة المحاولة عند الفشل."""
        manager = self._get_manager()
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await manager.embed_batch(
                    texts,
                    chunk_ids=chunk_ids,
                    article_id=article_id,
                    model_name=self.model_name,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"محاولة {attempt+1}/{self.max_retries} فشلت: {exc}"
                )
                await asyncio.sleep(self.retry_delay_s * (attempt + 1))
        raise RuntimeError(f"فشل embedding بعد {self.max_retries} محاولات: {last_error}")

    async def process(self, chunks, article_id: str) -> EmbedStageResult:
        """
        يستقبل قائمة DocumentChunk أو أي كائن يحمل (chunk_id, text).
        يُعيد EmbedStageResult مع جميع الـ records.
        """
        t0 = time.perf_counter()
        total = len(chunks)
        result = EmbedStageResult(article_id=article_id, total_chunks=total, embedded=0, failed=0)

        if not chunks:
            return result

        # تقسيم إلى batches
        for batch_start in range(0, total, self.batch_size):
            batch = chunks[batch_start : batch_start + self.batch_size]
            texts = [c.text for c in batch]
            ids = [c.chunk_id for c in batch]

            try:
                embeddings = await self._embed_with_retry(texts, ids, article_id)
                for chunk, emb in zip(batch, embeddings):
                    record = ChunkEmbeddingRecord(
                        chunk_id=chunk.chunk_id,
                        article_id=article_id,
                        text=chunk.text,
                        vector=emb.vector,
                        model_name=emb.model_name,
                        embedding_dim=emb.dimensions,
                        latency_ms=emb.latency_ms,
                        token_count=emb.token_count,
                    )
                    result.records.append(record)
                    result.embedded += 1
            except Exception as exc:
                logger.error(f"batch embedding فشل: {exc}")
                result.failed += len(batch)
                result.errors.append(str(exc))

        result.total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            f"embed_stage: {result.embedded}/{total} chunks — {result.total_ms:.1f}ms"
        )
        return result

    async def process_single(self, chunk, article_id: str) -> Optional[ChunkEmbeddingRecord]:
        """تضمين chunk واحد."""
        try:
            manager = self._get_manager()
            emb = await manager.embed(
                chunk.text,
                chunk_id=chunk.chunk_id,
                article_id=article_id,
                model_name=self.model_name,
            )
            return ChunkEmbeddingRecord(
                chunk_id=chunk.chunk_id,
                article_id=article_id,
                text=chunk.text,
                vector=emb.vector,
                model_name=emb.model_name,
                embedding_dim=emb.dimensions,
                latency_ms=emb.latency_ms,
                token_count=emb.token_count,
            )
        except Exception as exc:
            logger.error(f"embed_single فشل لـ {chunk.chunk_id}: {exc}")
            return None
