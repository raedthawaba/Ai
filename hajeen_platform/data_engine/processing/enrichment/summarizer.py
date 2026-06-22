"""Summarizer — section 5.11.

Lightweight extractive summarizer. No heavy ML models.

Algorithm:
1. Split text into sentences.
2. Score each sentence by word-frequency (TF-like scoring).
3. Optionally boost sentences that contain title words.
4. Return the top-N highest-scoring sentences in original order.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / patterns
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟\n])\s+")
_WORD_RE = re.compile(r"\b\w{3,}\b", re.UNICODE)

_ARABIC_STOP: frozenset[str] = frozenset({
    "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "التي",
    "الذي", "هو", "هي", "هم", "أن", "إن", "كان", "كانت", "لا", "ما",
    "لم", "لن", "قد", "أو", "لكن", "إذا", "بعد", "قبل", "بين", "كل",
})

_ENGLISH_STOP: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "not",
    "this", "that", "it", "its", "they", "their", "we", "you", "he", "she",
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SummarizerConfig:
    """Controls summarization behaviour."""

    max_sentences: int = 3
    min_sentence_length: int = 20
    title_boost: float = 1.5
    language: str = "ar"
    fallback_chars: int = 300
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core summarization logic
# ---------------------------------------------------------------------------

def _get_stop_words(language: str) -> frozenset:
    return _ARABIC_STOP if language == "ar" else _ENGLISH_STOP


def _split_sentences(text: str) -> List[str]:
    """Split text into non-empty sentences."""
    raw = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in raw if s.strip()]


def _word_freq(text: str, stop: frozenset) -> Counter:
    words = _WORD_RE.findall(text.lower())
    return Counter(w for w in words if w not in stop)


def _score_sentence(
    sentence: str,
    word_freq: Counter,
    title_words: frozenset,
    title_boost: float,
) -> float:
    """Score a sentence by summing word frequencies."""
    words = _WORD_RE.findall(sentence.lower())
    if not words:
        return 0.0
    score = sum(word_freq.get(w, 0) for w in words)
    # Boost sentences that contain title words
    overlap = sum(1 for w in words if w in title_words)
    score += overlap * title_boost
    return score / len(words)


def extractive_summarize(
    text: str,
    title: str = "",
    max_sentences: int = 3,
    min_sentence_length: int = 20,
    title_boost: float = 1.5,
    language: str = "ar",
) -> str:
    """Produce an extractive summary of *text*.

    Parameters
    ----------
    text:
        Article content.
    title:
        Article title (used for title-word boosting).
    max_sentences:
        Maximum sentences in the summary.
    min_sentence_length:
        Minimum char length for a sentence to be candidate.
    title_boost:
        Score multiplier for sentences containing title words.
    language:
        ``"ar"`` uses Arabic stop words; anything else uses English.

    Returns
    -------
    Summary string formed by the top-N ranked sentences in original order.
    """
    sentences = _split_sentences(text)
    candidates = [s for s in sentences if len(s) >= min_sentence_length]

    if not candidates:
        # Fallback: return first 300 chars
        return text.strip()[:300].rstrip()

    stop = _get_stop_words(language)
    freq = _word_freq(text, stop)
    title_words = frozenset(_WORD_RE.findall(title.lower()))

    scored = [
        (i, _score_sentence(s, freq, title_words, title_boost), s)
        for i, s in enumerate(candidates)
    ]

    # Select top-N by score
    top = sorted(scored, key=lambda x: x[1], reverse=True)[:max_sentences]
    # Restore original order
    top_sorted = sorted(top, key=lambda x: x[0])

    return " ".join(s for _, _, s in top_sorted)


# ---------------------------------------------------------------------------
# Summarizer class
# ---------------------------------------------------------------------------

class Summarizer:
    """Lightweight extractive summarizer.

    Parameters
    ----------
    config:
        :class:`SummarizerConfig`.
    """

    def __init__(self, config: Optional[SummarizerConfig] = None) -> None:
        self.config = config or SummarizerConfig()

    def summarize(self, text: str, title: str = "", language: Optional[str] = None) -> str:
        """Summarize *text*.

        Parameters
        ----------
        text:
            Content to summarize.
        title:
            Optional title for boosting.
        language:
            Override language; defaults to ``config.language``.

        Returns
        -------
        Extracted summary string.
        """
        if not text or not text.strip():
            return ""

        cfg = self.config
        lang = language or cfg.language

        return extractive_summarize(
            text=text,
            title=title,
            max_sentences=cfg.max_sentences,
            min_sentence_length=cfg.min_sentence_length,
            title_boost=cfg.title_boost,
            language=lang,
        )

    def summarize_article(self, article: Article) -> Article:
        """Return a new article with an extractive summary (if absent).

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        New Article with ``summary`` populated.
        """
        if article.summary and article.summary.strip():
            return article  # already has a summary

        lang = article.metadata.language or self.config.language
        summary = self.summarize(article.content, title=article.title, language=lang)

        if not summary:
            return article

        enriched = article.model_copy(update={"summary": summary})
        logger.debug(
            "Summarizer: id=%s summary_len=%d",
            article.id,
            len(summary),
        )
        return enriched

    def summarize_batch(self, articles: List[Article]) -> List[Article]:
        """Summarize a list of articles.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of Article copies with summaries.
        """
        result = [self.summarize_article(a) for a in articles]
        logger.info("Summarizer.summarize_batch: processed=%d", len(result))
        return result
