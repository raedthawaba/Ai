"""Keyword Extractor — section 5.9.

Extracts ranked keywords from article text using YAKE (Yet Another Keyword Extractor).

YAKE is a lightweight, unsupervised, statistical keyword extractor that works
well for Arabic and English without requiring training data or ML models.

Falls back to a TF-based frequency extractor when YAKE is unavailable.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional YAKE import
# ---------------------------------------------------------------------------

try:
    import yake  # type: ignore[import]
    _YAKE_AVAILABLE = True
except ImportError:
    _YAKE_AVAILABLE = False
    logger.info("keyword_extractor: yake not available; using frequency fallback")

# ---------------------------------------------------------------------------
# Stop words (for fallback)
# ---------------------------------------------------------------------------

_ARABIC_STOP: frozenset[str] = frozenset({
    "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك",
    "التي", "الذي", "هو", "هي", "هم", "أن", "إن", "كان", "كانت",
    "لا", "ما", "لم", "لن", "قد", "أو", "لكن", "إذا", "حتى", "بعد",
    "قبل", "بين", "عند", "منذ", "نحو", "حول", "وقد", "كما", "كل",
    "جميع", "بعض", "أي", "عبر", "أيضاً", "أيضا",
})

_ENGLISH_STOP: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "this", "that", "these", "those", "it", "its", "we", "you",
    "he", "she", "they", "them", "not", "no", "so", "yet", "both",
    "said", "also", "just", "about", "than", "then", "when", "where",
})

_WORD_RE = re.compile(r"\b\w{3,}\b", re.UNICODE)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class KeywordExtractorConfig:
    """Controls keyword extraction behaviour."""

    max_keywords: int = 10
    max_ngram_size: int = 2
    deduplication_threshold: float = 0.7
    language: str = "ar"              # "ar" or "en"
    min_word_length: int = 3
    min_freq: int = 1
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Keyword result
# ---------------------------------------------------------------------------

@dataclass
class Keyword:
    """A single extracted keyword with its score."""

    text: str
    score: float
    rank: int

    def __repr__(self) -> str:
        return f"Keyword({self.text!r}, score={self.score:.4f}, rank={self.rank})"


# ---------------------------------------------------------------------------
# YAKE-based extraction
# ---------------------------------------------------------------------------

def _yake_extract(
    text: str,
    language: str = "ar",
    max_keywords: int = 10,
    max_ngram: int = 2,
    dedup_threshold: float = 0.7,
) -> List[Keyword]:
    """Extract keywords using YAKE.

    Parameters
    ----------
    text:
        Input text.
    language:
        ISO language code (``"ar"``, ``"en"``).
    max_keywords:
        Maximum number of keywords to return.
    max_ngram:
        Maximum n-gram size.
    dedup_threshold:
        YAKE deduplication threshold.

    Returns
    -------
    List of :class:`Keyword` ranked by relevance (lower YAKE score = more relevant).
    """
    lang_map = {"ar": "ar", "en": "en"}
    yake_lang = lang_map.get(language, "en")

    extractor = yake.KeywordExtractor(
        lan=yake_lang,
        n=max_ngram,
        dedupLim=dedup_threshold,
        top=max_keywords,
        features=None,
    )

    raw = extractor.extract_keywords(text)
    # YAKE returns (keyword, score) — lower score = better relevance
    # Normalize to [0, 1] by inverting: relevance = 1 - norm(score)
    if not raw:
        return []

    max_score = max(s for _, s in raw) if raw else 1.0
    keywords: List[Keyword] = []
    for rank, (kw, score) in enumerate(raw, start=1):
        norm_score = 1.0 - (score / max_score) if max_score > 0 else 0.0
        keywords.append(Keyword(text=kw, score=round(norm_score, 4), rank=rank))

    return keywords


# ---------------------------------------------------------------------------
# Frequency-based fallback
# ---------------------------------------------------------------------------

def _freq_extract(
    text: str,
    language: str = "ar",
    max_keywords: int = 10,
    min_length: int = 3,
    min_freq: int = 1,
) -> List[Keyword]:
    """Extract keywords using word frequency (fallback).

    Parameters
    ----------
    text:
        Input text.
    language:
        ``"ar"`` uses Arabic stop words; anything else uses English.
    max_keywords:
        Maximum number of keywords.
    min_length:
        Minimum word character length.
    min_freq:
        Minimum frequency.

    Returns
    -------
    List of :class:`Keyword` ranked by frequency.
    """
    stop = _ARABIC_STOP if language == "ar" else _ENGLISH_STOP
    words = _WORD_RE.findall(text.lower())
    counts: Counter = Counter(
        w for w in words
        if len(w) >= min_length and w not in stop
    )

    if not counts:
        return []

    total = sum(counts.values())
    keywords: List[Keyword] = []
    for rank, (word, freq) in enumerate(counts.most_common(max_keywords), start=1):
        if freq < min_freq:
            break
        score = round(freq / total, 4)
        keywords.append(Keyword(text=word, score=score, rank=rank))

    return keywords


# ---------------------------------------------------------------------------
# KeywordExtractor class
# ---------------------------------------------------------------------------

class KeywordExtractor:
    """Extracts ranked keywords from article text.

    Uses YAKE when available, falls back to frequency-based extraction.

    Parameters
    ----------
    config:
        :class:`KeywordExtractorConfig`.
    """

    def __init__(self, config: Optional[KeywordExtractorConfig] = None) -> None:
        self.config = config or KeywordExtractorConfig()

    def extract_keywords(
        self,
        text: str,
        language: Optional[str] = None,
    ) -> List[Keyword]:
        """Extract keywords from *text*.

        Parameters
        ----------
        text:
            Input text (title + content recommended).
        language:
            Override language detection.  Falls back to ``config.language``.

        Returns
        -------
        List of :class:`Keyword` ordered by rank.
        """
        if not text or not text.strip():
            return []

        cfg = self.config
        lang = language or cfg.language

        if _YAKE_AVAILABLE:
            try:
                return _yake_extract(
                    text,
                    language=lang,
                    max_keywords=cfg.max_keywords,
                    max_ngram=cfg.max_ngram_size,
                    dedup_threshold=cfg.deduplication_threshold,
                )
            except Exception as exc:
                logger.debug("YAKE extraction failed: %s; using fallback", exc)

        return _freq_extract(
            text,
            language=lang,
            max_keywords=cfg.max_keywords,
            min_length=cfg.min_word_length,
            min_freq=cfg.min_freq,
        )

    def extract_article_keywords(self, article: Article) -> List[Keyword]:
        """Extract keywords from an article's title and content.

        Parameters
        ----------
        article:
            Article to process.

        Returns
        -------
        List of :class:`Keyword`.
        """
        text = article.title + " " + article.content
        lang = article.metadata.language or self.config.language
        return self.extract_keywords(text, language=lang)

    def enrich_article(self, article: Article) -> Article:
        """Return a new article enriched with extracted keyword tags.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        New Article with keyword tags merged into ``metadata.tags``.
        """
        keywords = self.extract_article_keywords(article)
        if not keywords:
            return article

        existing_tags = set(article.metadata.tags)
        new_tags = list(article.metadata.tags)
        for kw in keywords:
            if kw.text not in existing_tags:
                new_tags.append(kw.text)
                existing_tags.add(kw.text)

        new_meta = article.metadata.model_copy(update={"tags": new_tags})
        enriched = article.model_copy(update={"metadata": new_meta})

        logger.debug(
            "KeywordExtractor: id=%s keywords=%d",
            article.id,
            len(keywords),
        )
        return enriched

    def enrich_batch(self, articles: List[Article]) -> List[Article]:
        """Enrich a list of articles with keyword tags.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of enriched Article copies.
        """
        result = [self.enrich_article(a) for a in articles]
        logger.info("KeywordExtractor.enrich_batch: processed=%d", len(result))
        return result
