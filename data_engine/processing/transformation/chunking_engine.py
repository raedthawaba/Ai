"""Chunking Engine — Phase 6.5.

محرك تقسيم نصوص احترافي يدعم:
  - recursive chunking (الأسلوب الموصى به)
  - semantic chunking (تقسيم بناءً على الجمل والفقرات)
  - fixed chunking (حجم ثابت بالأحرف)
  - token-aware chunking (بالاستناد إلى عدد الـ tokens)
  
يُنتج DocumentChunk مع كامل البيانات الوصفية اللازمة للـ Embeddings.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── ثوابت ───────────────────────────────────────────────────────────────────

_PARAGRAPH_SEP = re.compile(r"\n{2,}")
_SENTENCE_END = re.compile(r"(?<=[.!?؟।\n])\s+")
_SENTENCE_END_STRICT = re.compile(r"[.!?؟]\s+")
_WHITESPACE_NORM = re.compile(r"\s+")
_CHARS_PER_TOKEN = 4  # تقدير خام: 1 رمز ≈ 4 أحرف


# ─────────────────────────────────────────────────────────────────────────────
# DocumentChunk — المخرج الأساسي
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentChunk:
    """قطعة نصية واحدة جاهزة للـ Embedding.

    المعرّف (chunk_id) محدد وثابت بناءً على محتوى القطعة
    ومعرّف المقال ورقم الترتيب — يمنع التكرار.
    """
    chunk_id: str
    article_id: str
    text: str
    token_count: int
    char_count: int
    order: int
    start_char: int
    end_char: int
    strategy: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── كائن التشابه ─────────────────────────────────────────────────────────
    content_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = _compute_chunk_hash(self.text)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @property
    def words(self) -> List[str]:
        return self.text.split()

    def __repr__(self) -> str:
        return (
            f"DocumentChunk(id={self.chunk_id[:12]}… "
            f"order={self.order} tokens={self.token_count} "
            f"chars={self.char_count})"
        )


def _compute_chunk_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _make_chunk_id(article_id: str, order: int, text: str) -> str:
    base = f"{article_id}::{order}::{_compute_chunk_hash(text)}"
    return "chk_" + hashlib.sha256(base.encode()).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

class ChunkingStrategy(str, Enum):
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"
    FIXED = "fixed"
    TOKEN_AWARE = "token_aware"


@dataclass
class ChunkingConfig:
    """إعدادات محرك التقسيم."""

    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 512       # بالأحرف (fixed) أو الـ tokens (token_aware)
    overlap: int = 64            # أحرف أو tokens للتداخل بين القطع
    min_chunk_chars: int = 50   # حد أدنى لطول القطعة
    max_chunk_chars: int = 4096  # حد أقصى لطول القطعة
    max_chunks_per_article: Optional[int] = None
    # Recursive chunking separators (بالترتيب التنازلي للأولوية)
    separators: List[str] = field(
        default_factory=lambda: ["\n\n", "\n", ". ", "؟ ", "! ", " ", ""]
    )
    # Semantic chunking
    sentence_min_chars: int = 30
    # Token-aware
    chars_per_token_override: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Splitters الأساسية
# ─────────────────────────────────────────────────────────────────────────────

def _split_by_separator(text: str, separator: str) -> List[str]:
    """تقسيم نص بفاصل محدد."""
    if not separator:
        return list(text)
    parts = text.split(separator)
    return [p for p in parts if p.strip()]


def _merge_splits(
    splits: List[str],
    max_chars: int,
    overlap_chars: int,
    min_chars: int,
    separator: str = " ",
) -> List[str]:
    """دمج الأجزاء في chunks بحجم أقصى مع دعم التداخل."""
    chunks: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for split in splits:
        split_len = len(split)
        if current_len + split_len + len(separator) > max_chars and current_parts:
            combined = separator.join(current_parts).strip()
            if len(combined) >= min_chars:
                chunks.append(combined)
            # إنشاء التداخل
            overlap_text = combined[-overlap_chars:] if overlap_chars else ""
            current_parts = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)
        current_parts.append(split)
        current_len += split_len + len(separator)

    if current_parts:
        combined = separator.join(current_parts).strip()
        if len(combined) >= min_chars:
            chunks.append(combined)

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# استراتيجيات التقسيم
# ─────────────────────────────────────────────────────────────────────────────

def _recursive_split(
    text: str,
    separators: List[str],
    max_chars: int,
    overlap_chars: int,
    min_chars: int,
) -> List[str]:
    """Recursive Character Text Splitting.
    
    يُقسّم بالفاصل الأعلى أولوية؛ إذا كانت القطع لا تزال كبيرة،
    يُكرر العملية بالفاصل التالي.
    """
    stripped = text.strip()
    if not stripped:
        return []

    # إذا كان النص أصغر من الحجم المطلوب → أعِده مباشرة
    if len(stripped) <= max_chars:
        return [stripped] if len(stripped) >= min_chars else []

    separator = separators[0] if separators else ""
    next_separators = separators[1:] if len(separators) > 1 else [""]

    splits = _split_by_separator(text, separator)

    result: List[str] = []
    good_splits: List[str] = []

    for split in splits:
        if len(split) <= max_chars:
            good_splits.append(split)
        else:
            # القطعة لا تزال كبيرة — نُقسّمها مرة أخرى
            if good_splits:
                result.extend(_merge_splits(
                    good_splits, max_chars, overlap_chars, min_chars, separator
                ))
                good_splits = []
            result.extend(_recursive_split(
                split, next_separators, max_chars, overlap_chars, min_chars
            ))

    if good_splits:
        result.extend(_merge_splits(
            good_splits, max_chars, overlap_chars, min_chars, separator
        ))

    return result


def _semantic_split(
    text: str,
    max_chars: int,
    overlap_chars: int,
    min_chars: int,
    sentence_min_chars: int = 30,
) -> List[str]:
    """Semantic Splitting — تقسيم بناءً على الجمل والفقرات."""
    # 1. تقسيم الفقرات
    paragraphs = _PARAGRAPH_SEP.split(text.strip())

    sentences: List[str] = []
    for para in paragraphs:
        # تقسيم الجمل داخل كل فقرة
        sents = _SENTENCE_END.split(para.strip())
        for s in sents:
            s = s.strip()
            if len(s) >= sentence_min_chars:
                sentences.append(s)
            elif sentences:
                # دمج الجملة القصيرة مع السابقة
                sentences[-1] = sentences[-1] + " " + s
        # فاصل فقرة = سطر فارغ يُضاف كحد
        if sentences:
            sentences.append("")  # placeholder للفقرة

    # 2. دمج الجمل في chunks
    chunks: List[str] = []
    current = ""
    for sent in sentences:
        if not sent:
            if current.strip():
                chunks.append(current.strip())
                current = current[-overlap_chars:] if overlap_chars else ""
            continue
        if len(current) + len(sent) + 1 <= max_chars:
            current = (current + " " + sent).strip()
        else:
            if len(current) >= min_chars:
                chunks.append(current.strip())
            overlap = current[-overlap_chars:] if overlap_chars else ""
            current = (overlap + " " + sent).strip() if overlap else sent

    if len(current) >= min_chars:
        chunks.append(current.strip())

    return [c for c in chunks if len(c) >= min_chars]


def _fixed_split(
    text: str,
    chunk_size: int,
    overlap: int,
    min_chars: int,
) -> List[str]:
    """Fixed-size splitting بعدد ثابت من الأحرف."""
    chunks: List[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if len(chunk) >= min_chars:
            chunks.append(chunk)
        # التقدّم دائماً للأمام — تجنّب infinite loop عند نهاية النص
        if end >= length:
            break
        next_start = end - overlap if (overlap > 0 and overlap < chunk_size) else end
        if next_start <= start:
            next_start = start + 1  # ضمان التقدّم
        start = next_start
    return chunks


def _token_aware_split(
    text: str,
    max_tokens: int,
    overlap_tokens: int,
    min_chars: int,
    chars_per_token: int = _CHARS_PER_TOKEN,
) -> List[str]:
    """Token-aware splitting — يُقدّر عدد الـ tokens."""
    char_size = max_tokens * chars_per_token
    char_overlap = overlap_tokens * chars_per_token
    return _fixed_split(text, char_size, char_overlap, min_chars)


# ─────────────────────────────────────────────────────────────────────────────
# ChunkingEngine — الواجهة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────

class ChunkingEngine:
    """محرك تقسيم النصوص الاحترافي لـ Phase 6.5.
    
    Parameters
    ----------
    config:
        ChunkingConfig للتحكم في أسلوب التقسيم.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None) -> None:
        self.config = config or ChunkingConfig()

    def chunk_text(
        self,
        text: str,
        article_id: str = "unknown",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        """تقسيم نص إلى DocumentChunks.

        Parameters
        ----------
        text:
            النص المراد تقسيمه.
        article_id:
            معرّف المقال المصدر.
        extra_metadata:
            بيانات وصفية إضافية تُضاف لكل chunk.

        Returns
        -------
        List[DocumentChunk]
        """
        if not text or not text.strip():
            return []

        cfg = self.config
        raw_chunks = list(self._split(text))

        if not raw_chunks:
            return []

        # تطبيق الحد الأقصى
        if cfg.max_chunks_per_article:
            raw_chunks = raw_chunks[: cfg.max_chunks_per_article]

        chunks: List[DocumentChunk] = []
        cursor = 0

        for order, chunk_text in enumerate(raw_chunks):
            chunk_text = chunk_text.strip()
            if len(chunk_text) < cfg.min_chunk_chars:
                continue

            # إيجاد موضع الـ chunk في النص الأصلي
            start = text.find(chunk_text, cursor)
            if start == -1:
                start = cursor
            end = start + len(chunk_text)
            cursor = max(cursor, start + 1)

            token_count = _estimate_tokens(chunk_text)
            chunk_id = _make_chunk_id(article_id, order, chunk_text)

            meta: Dict[str, Any] = {
                "strategy": cfg.strategy.value,
                "article_id": article_id,
                "order": order,
                **(extra_metadata or {}),
            }

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    article_id=article_id,
                    text=chunk_text,
                    token_count=token_count,
                    char_count=len(chunk_text),
                    order=order,
                    start_char=start,
                    end_char=end,
                    strategy=cfg.strategy.value,
                    metadata=meta,
                )
            )

        logger.debug(
            "ChunkingEngine: article=%s strategy=%s chunks=%d",
            article_id, cfg.strategy.value, len(chunks),
        )
        return chunks

    def chunk_article(self, article: Any) -> List[DocumentChunk]:
        """تقسيم مقال UnifiedArticle أو Article قديم.

        Parameters
        ----------
        article:
            UnifiedArticle أو Article.

        Returns
        -------
        List[DocumentChunk]
        """
        from shared.schemas.unified_article import UnifiedArticle
        from shared.schemas.article import Article

        if isinstance(article, UnifiedArticle):
            text = article.content_for_processing()
            article_id = article.id
            language = article.language
        elif isinstance(article, Article):
            text = article.content
            article_id = article.id
            language = article.metadata.language
        else:
            logger.warning("ChunkingEngine: نوع مقال غير مدعوم: %s", type(article))
            return []

        return self.chunk_text(
            text,
            article_id=article_id,
            extra_metadata={"language": language},
        )

    def chunk_batch(
        self,
        articles: List[Any],
    ) -> List[Tuple[Any, List[DocumentChunk]]]:
        """تقسيم دُفعة من المقالات.

        Returns
        -------
        List of (article, chunks) tuples.
        """
        results = []
        total_chunks = 0
        for article in articles:
            chunks = self.chunk_article(article)
            results.append((article, chunks))
            total_chunks += len(chunks)

        logger.info(
            "ChunkingEngine.chunk_batch: articles=%d total_chunks=%d avg=%.1f",
            len(articles),
            total_chunks,
            total_chunks / len(articles) if articles else 0,
        )
        return results

    # ── Internal ──────────────────────────────────────────────────────────────

    def _split(self, text: str) -> List[str]:
        cfg = self.config

        if cfg.strategy == ChunkingStrategy.FIXED:
            return _fixed_split(
                text, cfg.chunk_size, cfg.overlap, cfg.min_chunk_chars
            )

        if cfg.strategy == ChunkingStrategy.TOKEN_AWARE:
            cpt = cfg.chars_per_token_override or _CHARS_PER_TOKEN
            return _token_aware_split(
                text, cfg.chunk_size, cfg.overlap, cfg.min_chunk_chars, cpt
            )

        if cfg.strategy == ChunkingStrategy.SEMANTIC:
            return _semantic_split(
                text, cfg.chunk_size, cfg.overlap,
                cfg.min_chunk_chars, cfg.sentence_min_chars,
            )

        # Default: RECURSIVE
        return _recursive_split(
            text, cfg.separators,
            cfg.chunk_size, cfg.overlap, cfg.min_chunk_chars,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Chunk Deduplicator — يمنع تكرار الـ chunks
# ─────────────────────────────────────────────────────────────────────────────

class ChunkDeduplicator:
    """يمنع تخزين chunks مكرّرة عبر دُفعات متعددة."""

    def __init__(self) -> None:
        self._seen_hashes: set[str] = set()

    def deduplicate(
        self, chunks: List[DocumentChunk]
    ) -> Tuple[List[DocumentChunk], List[str]]:
        """إزالة الـ chunks المكرّرة.

        Returns
        -------
        (unique_chunks, duplicate_ids)
        """
        unique: List[DocumentChunk] = []
        dup_ids: List[str] = []

        for chunk in chunks:
            if chunk.content_hash in self._seen_hashes:
                dup_ids.append(chunk.chunk_id)
                logger.debug(
                    "ChunkDedup: تكرار chunk_id=%s", chunk.chunk_id
                )
            else:
                self._seen_hashes.add(chunk.content_hash)
                unique.append(chunk)

        if dup_ids:
            logger.info(
                "ChunkDedup: %d chunks فريدة، %d مكرّرة",
                len(unique), len(dup_ids),
            )

        return unique, dup_ids

    def reset(self) -> None:
        """إعادة تعيين الحالة."""
        self._seen_hashes.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_chunking_engine(
    strategy: str = "recursive",
    chunk_size: int = 512,
    overlap: int = 64,
    **kwargs: Any,
) -> ChunkingEngine:
    """إنشاء ChunkingEngine بإعدادات مبسّطة.

    Parameters
    ----------
    strategy:
        "recursive" | "semantic" | "fixed" | "token_aware"
    chunk_size:
        حجم الـ chunk بالأحرف أو الـ tokens.
    overlap:
        التداخل بين القطع.
    """
    config = ChunkingConfig(
        strategy=ChunkingStrategy(strategy),
        chunk_size=chunk_size,
        overlap=overlap,
        **{k: v for k, v in kwargs.items() if hasattr(ChunkingConfig, k)},
    )
    return ChunkingEngine(config)
