"""Transformation Pipeline — Phase 2 (Section 2.5).

Pipeline تحويل موحّد يجمع:
  1. TokenizerWrapper  — عد الـ tokens وتقطيعها
  2. ChunkingEngine   — recursive / semantic / fixed / token-aware chunking
  3. TextChunker      — مُحسَّن للتوافق
  4. MarkdownConverter — تحويل إلى Markdown
  5. DataTransformer  — تصدير JSON/JSONL/CSV

يُنتج TransformationOutput موحّد يحتوي على:
  - article_id
  - chunks (DocumentChunks)
  - markdown_content
  - transformed_data (dict)
  - metrics
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from shared.schemas.article import Article
from .tokenizer_wrapper import TokenizerWrapper, TokenizerConfig
from .chunking_engine import ChunkingEngine, ChunkingConfig, DocumentChunk
from .markdown_converter import MarkdownConverter, MarkdownConverterConfig
from .data_transformer import DataTransformer, TransformerConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TransformationPipelineConfig:
    """إعدادات Transformation Pipeline الموحّد."""

    # تفعيل / تعطيل كل مرحلة
    use_tokenizer: bool = True
    use_chunker: bool = True
    use_markdown_converter: bool = True
    use_data_transformer: bool = True

    # قيود الـ tokens
    max_tokens_per_article: Optional[int] = None    # None = بلا حد
    truncate_if_over_limit: bool = True

    # إعدادات كل مرحلة
    tokenizer_config: Optional[TokenizerConfig] = None
    chunking_config: Optional[ChunkingConfig] = None
    markdown_config: Optional[MarkdownConverterConfig] = None
    transformer_config: Optional[TransformerConfig] = None

    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Transformation Output
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TransformationOutput:
    """مخرجات تحويل مقال واحد."""
    article_id: str
    chunks: List[DocumentChunk] = field(default_factory=list)
    total_tokens: int = 0
    was_truncated: bool = False
    markdown_content: str = ""
    transformed_data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def chunk_ids(self) -> List[str]:
        return [c.chunk_id for c in self.chunks]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "chunk_count": self.chunk_count,
            "total_tokens": self.total_tokens,
            "was_truncated": self.was_truncated,
            "has_markdown": bool(self.markdown_content),
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


@dataclass
class TransformationMetrics:
    """إحصائيات تحويل دُفعة كاملة."""
    total_input: int = 0
    total_transformed: int = 0
    total_errors: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    total_truncated: int = 0
    total_duration_ms: float = 0.0
    article_outputs: List[TransformationOutput] = field(default_factory=list)

    @property
    def avg_chunks_per_article(self) -> float:
        return self.total_chunks / self.total_transformed if self.total_transformed else 0.0

    @property
    def avg_tokens_per_article(self) -> float:
        return self.total_tokens / self.total_transformed if self.total_transformed else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input": self.total_input,
            "total_transformed": self.total_transformed,
            "total_errors": self.total_errors,
            "total_chunks": self.total_chunks,
            "avg_chunks_per_article": round(self.avg_chunks_per_article, 2),
            "avg_tokens_per_article": round(self.avg_tokens_per_article, 2),
            "total_truncated": self.total_truncated,
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# TransformationPipeline
# ─────────────────────────────────────────────────────────────────────────────

class TransformationPipeline:
    """Pipeline تحويل موحّد من Article → Chunks + Markdown + JSON.

    Parameters
    ----------
    config:
        TransformationPipelineConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[TransformationPipelineConfig] = None) -> None:
        self.config = config or TransformationPipelineConfig()

        # تهيئة المعالجات (lazy-safe — تُهيّأ هنا لأنها خفيفة)
        self._tokenizer = (
            TokenizerWrapper(self.config.tokenizer_config)
            if self.config.use_tokenizer
            else None
        )
        self._chunker = (
            ChunkingEngine(self.config.chunking_config)
            if self.config.use_chunker
            else None
        )
        self._markdown = (
            MarkdownConverter(self.config.markdown_config)
            if self.config.use_markdown_converter
            else None
        )
        self._transformer = (
            DataTransformer(self.config.transformer_config)
            if self.config.use_data_transformer
            else None
        )

    # ─── Single article transformation ────────────────────────────────────

    def transform_article(self, article: Article) -> TransformationOutput:
        """تحويل مقال واحد.

        Parameters
        ----------
        article:
            المقال المصدر.

        Returns
        -------
        TransformationOutput مع chunks, markdown, transformed_data.
        """
        cfg = self.config
        start = time.monotonic()
        output = TransformationOutput(article_id=article.id)
        content = article.content

        try:
            # 1. Token counting + truncation
            if self._tokenizer:
                output.total_tokens = self._tokenizer.count_tokens(content)

                if cfg.max_tokens_per_article and output.total_tokens > cfg.max_tokens_per_article:
                    if cfg.truncate_if_over_limit:
                        content = self._tokenizer.truncate_tokens(
                            content, cfg.max_tokens_per_article
                        )
                        output.was_truncated = True
                        output.total_tokens = cfg.max_tokens_per_article
                        logger.debug(
                            "TransformationPipeline: truncated id=%s "
                            "tokens=%d→%d",
                            article.id,
                            self._tokenizer.count_tokens(article.content),
                            cfg.max_tokens_per_article,
                        )

            # استخدم المحتوى المقطوع للخطوات التالية
            working_article = (
                article.model_copy(update={"content": content})
                if content != article.content
                else article
            )

            # 2. Chunking
            if self._chunker:
                output.chunks = self._chunker.chunk_article(working_article)
                logger.debug(
                    "TransformationPipeline: id=%s chunks=%d",
                    article.id, len(output.chunks),
                )

            # 3. Markdown conversion
            if self._markdown:
                output.markdown_content = self._markdown.article_to_markdown(working_article)

            # 4. Data transformation
            if self._transformer:
                output.transformed_data = self._transformer.transform(working_article)

        except Exception as exc:
            logger.error(
                "TransformationPipeline: خطأ في تحويل id=%s — %s",
                article.id, exc,
            )
            output.error = str(exc)

        output.duration_ms = (time.monotonic() - start) * 1000
        return output

    # ─── Batch transformation ──────────────────────────────────────────────

    def transform_batch(
        self, articles: List[Article]
    ) -> Tuple[List[TransformationOutput], TransformationMetrics]:
        """تحويل دُفعة من المقالات.

        Parameters
        ----------
        articles:
            قائمة المقالات.

        Returns
        -------
        (outputs, metrics)
        """
        metrics = TransformationMetrics(total_input=len(articles))
        outputs: List[TransformationOutput] = []

        for article in articles:
            output = self.transform_article(article)
            outputs.append(output)
            metrics.article_outputs.append(output)
            metrics.total_duration_ms += output.duration_ms
            metrics.total_chunks += output.chunk_count
            metrics.total_tokens += output.total_tokens

            if output.was_truncated:
                metrics.total_truncated += 1

            if output.error:
                metrics.total_errors += 1
            else:
                metrics.total_transformed += 1

        logger.info(
            "TransformationPipeline.transform_batch: in=%d out=%d "
            "chunks=%d avg_chunks=%.1f errors=%d",
            metrics.total_input,
            metrics.total_transformed,
            metrics.total_chunks,
            metrics.avg_chunks_per_article,
            metrics.total_errors,
        )
        return outputs, metrics

    # ─── Async API ─────────────────────────────────────────────────────────

    async def async_transform_article(
        self, article: Article
    ) -> TransformationOutput:
        """تحويل مقال بشكل async."""
        return await asyncio.to_thread(self.transform_article, article)

    async def async_transform_batch(
        self, articles: List[Article], max_concurrency: int = 8
    ) -> Tuple[List[TransformationOutput], TransformationMetrics]:
        """تحويل دُفعة من المقالات بالتوازي."""
        sem = asyncio.Semaphore(max_concurrency)

        async def _one(a: Article) -> TransformationOutput:
            async with sem:
                return await self.async_transform_article(a)

        outputs = await asyncio.gather(*[_one(a) for a in articles])
        outputs = list(outputs)

        metrics = TransformationMetrics(total_input=len(articles))
        for output in outputs:
            metrics.article_outputs.append(output)
            metrics.total_duration_ms += output.duration_ms
            metrics.total_chunks += output.chunk_count
            metrics.total_tokens += output.total_tokens
            if output.was_truncated:
                metrics.total_truncated += 1
            if output.error:
                metrics.total_errors += 1
            else:
                metrics.total_transformed += 1

        return outputs, metrics

    # ─── Helpers ───────────────────────────────────────────────────────────

    def get_all_chunks(
        self, outputs: List[TransformationOutput]
    ) -> List[DocumentChunk]:
        """استخراج جميع chunks من مخرجات دُفعة.

        Parameters
        ----------
        outputs:
            قائمة TransformationOutput.

        Returns
        -------
        List[DocumentChunk] لجميع المقالات.
        """
        return [chunk for output in outputs for chunk in output.chunks]

    def export_to_jsonl(
        self, outputs: List[TransformationOutput]
    ) -> str:
        """تصدير مخرجات الدُفعة إلى JSONL.

        Returns
        -------
        سلسلة JSONL.
        """
        import json
        lines = [
            json.dumps(o.to_dict(), ensure_ascii=False)
            for o in outputs
        ]
        return "\n".join(lines)
