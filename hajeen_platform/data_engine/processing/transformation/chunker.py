"""Chunker — section 5.12.

Splits long texts into overlapping chunks for downstream processing.

Strategies:
- ``paragraph``: Split on double-newlines / paragraph boundaries.
- ``sentence``:  Split on sentence-ending punctuation.
- ``fixed``:     Split by fixed character count.
- ``token_estimate``: Split by estimated token count (no tokenizer required).

All strategies support configurable ``chunk_size`` and ``overlap``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PARA_SPLIT = re.compile(r"\n{2,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+")
_WHITESPACE_NORM = re.compile(r"\s+")

# Rough token estimate: 1 token ≈ 4 chars (works for Arabic and English)
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ChunkerConfig:
    """Controls text chunking behaviour."""

    strategy: str = "paragraph"   # "paragraph" | "sentence" | "fixed" | "token_estimate"
    chunk_size: int = 512          # chars (fixed) or tokens (token_estimate)
    overlap: int = 64              # chars or tokens of overlap
    min_chunk_length: int = 20    # skip chunks shorter than this
    max_chunks: Optional[int] = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A single text chunk."""

    index: int
    text: str
    start_char: int
    end_char: int
    estimated_tokens: int

    @property
    def char_length(self) -> int:
        return len(self.text)

    def __repr__(self) -> str:
        return (
            f"Chunk(index={self.index} "
            f"chars={self.char_length} "
            f"tokens≈{self.estimated_tokens})"
        )


# ---------------------------------------------------------------------------
# Low-level splitting helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Estimate token count from character count."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_paragraph(text: str) -> List[str]:
    parts = _PARA_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_sentence(text: str) -> List[str]:
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _merge_with_overlap(
    parts: List[str],
    max_chars: int,
    overlap_chars: int,
    min_length: int,
) -> List[str]:
    """Merge short parts into chunks of at most *max_chars* characters,
    with *overlap_chars* of trailing overlap between consecutive chunks."""
    chunks: List[str] = []
    current = ""

    for part in parts:
        if len(current) + len(part) + 1 <= max_chars:
            current = (current + " " + part).strip()
        else:
            if len(current) >= min_length:
                chunks.append(current)
            # Start next chunk with overlap from the end of current
            overlap_text = current[-overlap_chars:] if overlap_chars else ""
            current = (overlap_text + " " + part).strip() if overlap_text else part

    if len(current) >= min_length:
        chunks.append(current)

    return chunks


def _fixed_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split by fixed character count."""
    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        start = end - overlap if overlap < chunk_size else end

    return chunks


# ---------------------------------------------------------------------------
# Chunker class
# ---------------------------------------------------------------------------

class TextChunker:
    """Splits long texts into manageable chunks.

    Parameters
    ----------
    config:
        :class:`ChunkerConfig`.
    """

    def __init__(self, config: Optional[ChunkerConfig] = None) -> None:
        self.config = config or ChunkerConfig()

    def chunk_text(self, text: str) -> List[Chunk]:
        """Split *text* into chunks according to config.

        Parameters
        ----------
        text:
            Input text to split.

        Returns
        -------
        List of :class:`Chunk`.
        """
        if not text or not text.strip():
            return []

        cfg = self.config
        raw_chunks = self._split(text)

        if not raw_chunks:
            return []

        # Build Chunk objects with character offsets
        chunks: List[Chunk] = []
        cursor = 0
        for i, chunk_text in enumerate(raw_chunks):
            if len(chunk_text) < cfg.min_chunk_length:
                continue
            # Find the chunk start position in original text
            start = text.find(chunk_text, cursor)
            if start == -1:
                start = cursor
            end = start + len(chunk_text)
            cursor = max(cursor, start + 1)

            chunks.append(
                Chunk(
                    index=i,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                    estimated_tokens=_estimate_tokens(chunk_text),
                )
            )

            if cfg.max_chunks and len(chunks) >= cfg.max_chunks:
                break

        logger.debug(
            "TextChunker: strategy=%s chunks=%d total_chars=%d",
            cfg.strategy,
            len(chunks),
            len(text),
        )
        return chunks

    def chunk_article(self, article: Article) -> List[Chunk]:
        """Chunk an article's content.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        List of :class:`Chunk`.
        """
        chunks = self.chunk_text(article.content)
        logger.debug("TextChunker: id=%s chunks=%d", article.id, len(chunks))
        return chunks

    def chunk_batch(
        self, articles: List[Article]
    ) -> List[tuple]:
        """Chunk a list of articles.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of ``(article, chunks)`` tuples.
        """
        result = [(a, self.chunk_article(a)) for a in articles]
        logger.info(
            "TextChunker.chunk_batch: articles=%d total_chunks=%d",
            len(articles),
            sum(len(c) for _, c in result),
        )
        return result

    # ------------------------------------------------------------------
    # Internal splitting
    # ------------------------------------------------------------------

    def _split(self, text: str) -> List[str]:
        cfg = self.config
        strategy = cfg.strategy
        chunk_size = cfg.chunk_size
        overlap = cfg.overlap
        min_len = cfg.min_chunk_length

        if strategy == "fixed":
            return _fixed_split(text, chunk_size, overlap)

        if strategy == "token_estimate":
            char_size = chunk_size * _CHARS_PER_TOKEN
            char_overlap = overlap * _CHARS_PER_TOKEN
            return _fixed_split(text, char_size, char_overlap)

        if strategy == "sentence":
            parts = _split_sentence(text)
            return _merge_with_overlap(parts, chunk_size, overlap, min_len)

        # Default: paragraph
        parts = _split_paragraph(text)
        if not parts:
            parts = _split_sentence(text)
        return _merge_with_overlap(parts, chunk_size, overlap, min_len)
