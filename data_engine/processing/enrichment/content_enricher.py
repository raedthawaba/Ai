"""Content Enricher — section 4.12.

Enriches articles with derived metadata without external ML dependencies.

Capabilities:
- Extractive summarisation (leading sentences)
- Reading-time estimation (Arabic & Latin)
- Keyword / tag extraction (TF-ish frequency + title boost)
- Named-entity hint extraction (patterns for dates, organisations, hashtags)
- Language detection integration
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from shared.schemas.article import Article, ArticleEntity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ARABIC_STOP_WORDS: frozenset[str] = frozenset(
    {
        "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك",
        "التي", "الذي", "التي", "هو", "هي", "هم", "أن", "إن", "كان", "كانت",
        "يكون", "تكون", "لا", "ما", "لم", "لن", "قد", "فإن", "ولا", "أو",
        "لكن", "إذا", "حتى", "بعد", "قبل", "خلال", "بين", "عند", "منذ",
        "نحو", "حول", "ضد", "مع", "له", "لها", "لهم", "به", "بها", "بهم",
        "وقد", "وكان", "وكانت", "وهو", "وهي", "كما", "أيضاً", "أيضا",
        "كل", "جميع", "بعض", "أي", "كيف", "متى", "أين", "لماذا", "كم",
    }
)

_ENGLISH_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "through", "during",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may", "might",
        "shall", "can", "this", "that", "these", "those", "it", "its", "we",
        "you", "he", "she", "they", "them", "their", "our", "my", "your",
        "his", "her", "what", "which", "who", "whom", "when", "where", "how",
        "not", "no", "nor", "so", "yet", "both", "either", "neither",
    }
)

_WPM_ARABIC = 138
_WPM_LATIN = 200
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?؟])\s+")
_WORD_RE = re.compile(r"\b\w{3,}\b", re.UNICODE)
_HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
_DATE_HINT_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
    re.UNICODE,
)
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EnricherConfig:
    """Controls the enrichment behaviour."""

    max_summary_sentences: int = 3
    max_keywords: int = 10
    min_keyword_length: int = 3
    min_keyword_freq: int = 1
    title_boost: int = 3
    extract_hashtags: bool = True
    extract_date_hints: bool = True
    enrich_tags: bool = True
    estimate_reading_time: bool = True
    generate_summary: bool = True
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> List[str]:
    """Split *text* into sentences using punctuation boundaries.

    Parameters
    ----------
    text:
        Input text.

    Returns
    -------
    List of sentence strings (stripped, non-empty).
    """
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def extractive_summary(text: str, max_sentences: int = 3) -> str:
    """Return the first *max_sentences* sentences as an extractive summary.

    Parameters
    ----------
    text:
        Input text.
    max_sentences:
        Maximum number of leading sentences to include.

    Returns
    -------
    Summary string.
    """
    sentences = split_sentences(text)
    return " ".join(sentences[:max_sentences])


def estimate_reading_time(text: str) -> int:
    """Estimate reading time in seconds.

    Uses different words-per-minute rates for Arabic (138 wpm) vs Latin (200 wpm).

    Parameters
    ----------
    text:
        Input text.

    Returns
    -------
    Estimated reading time in seconds (minimum 1).
    """
    words = _WORD_RE.findall(text)
    if not words:
        return 1
    arabic_chars = sum(len(_ARABIC_CHAR_RE.findall(w)) for w in words)
    total_chars = sum(len(w) for w in words)
    arabic_ratio = arabic_chars / total_chars if total_chars else 0
    wpm = _WPM_ARABIC if arabic_ratio >= 0.5 else _WPM_LATIN
    seconds = max(1, round((len(words) / wpm) * 60))
    return seconds


def extract_keywords(
    text: str,
    language: str = "en",
    max_keywords: int = 10,
    min_length: int = 3,
    min_freq: int = 1,
    title_text: str = "",
    title_boost: int = 3,
) -> List[str]:
    """Extract the top keywords from *text* using word frequency.

    Words from *title_text* receive a frequency boost proportional to
    *title_boost* (they are counted as if they appeared that many extra times).

    Parameters
    ----------
    text:
        Main content to analyse.
    language:
        ``"ar"`` uses Arabic stop words; anything else uses English stop words.
    max_keywords:
        Maximum number of keywords to return.
    min_length:
        Minimum character length for a word to be a candidate.
    min_freq:
        Minimum frequency for a word to be included.
    title_text:
        Title text whose words receive a boost.
    title_boost:
        Number of extra occurrences added for each title word.

    Returns
    -------
    List of keyword strings ordered by frequency (descending).
    """
    stop_words = _ARABIC_STOP_WORDS if language == "ar" else _ENGLISH_STOP_WORDS

    words = _WORD_RE.findall(text.lower())
    title_words = _WORD_RE.findall(title_text.lower())

    counts: Counter = Counter()
    for w in words:
        if len(w) >= min_length and w not in stop_words:
            counts[w] += 1

    for w in title_words:
        if len(w) >= min_length and w not in stop_words:
            counts[w] += title_boost

    return [w for w, c in counts.most_common(max_keywords) if c >= min_freq]


def extract_hashtags(text: str) -> List[str]:
    """Extract ``#hashtag`` tokens from *text*.

    Parameters
    ----------
    text:
        Input string.

    Returns
    -------
    List of hashtag strings without the leading ``#``.
    """
    return _HASHTAG_RE.findall(text)


def extract_date_hints(text: str) -> List[ArticleEntity]:
    """Extract date-like patterns as :class:`ArticleEntity` hints.

    Parameters
    ----------
    text:
        Input text to scan.

    Returns
    -------
    List of ArticleEntity objects with ``label="DATE"``.
    """
    entities = []
    for m in _DATE_HINT_RE.finditer(text):
        try:
            entities.append(
                ArticleEntity(
                    text=m.group(),
                    label="DATE",
                    start_char=m.start(),
                    end_char=m.end(),
                    score=0.8,
                )
            )
        except Exception:
            pass
    return entities


# ---------------------------------------------------------------------------
# Article-level enricher
# ---------------------------------------------------------------------------

class ContentEnricher:
    """Enriches articles with derived metadata.

    Parameters
    ----------
    config:
        :class:`EnricherConfig` controlling enrichment steps.
    """

    def __init__(self, config: Optional[EnricherConfig] = None) -> None:
        self.config = config or EnricherConfig()

    def enrich_article(self, article: Article) -> Article:
        """Return a new :class:`Article` enriched with derived metadata.

        Enrichment adds / overwrites:
        - ``summary`` — extractive summary (if missing or config allows)
        - ``metadata.tags`` — keyword-based tags merged with existing
        - ``metadata.entities`` — date-hint entities merged with existing
        - ``metadata.extra["reading_time_seconds"]``

        Parameters
        ----------
        article:
            Source article to enrich.

        Returns
        -------
        New Article instance with enriched fields.
        """
        cfg = self.config
        updates: dict = {}

        if cfg.generate_summary and not article.summary:
            summary = extractive_summary(
                article.content, max_sentences=cfg.max_summary_sentences
            )
            if summary:
                updates["summary"] = summary

        new_extra = dict(article.metadata.extra)

        if cfg.estimate_reading_time:
            rtime = estimate_reading_time(article.content)
            new_extra["reading_time_seconds"] = rtime

        new_tags = list(article.metadata.tags)
        if cfg.enrich_tags:
            keywords = extract_keywords(
                text=article.content,
                language=article.metadata.language,
                max_keywords=cfg.max_keywords,
                min_length=cfg.min_keyword_length,
                min_freq=cfg.min_keyword_freq,
                title_text=article.title,
                title_boost=cfg.title_boost,
            )
            for kw in keywords:
                if kw not in new_tags:
                    new_tags.append(kw)

        if cfg.extract_hashtags:
            for ht in extract_hashtags(article.title + " " + article.content):
                tag = ht.lower()
                if tag not in new_tags:
                    new_tags.append(tag)

        new_entities = list(article.metadata.entities)
        if cfg.extract_date_hints:
            existing_spans = {(e.start_char, e.end_char) for e in new_entities}
            for ent in extract_date_hints(article.content):
                if (ent.start_char, ent.end_char) not in existing_spans:
                    new_entities.append(ent)

        new_metadata = article.metadata.model_copy(
            update={
                "tags": new_tags,
                "entities": new_entities,
                "extra": new_extra,
            }
        )
        updates["metadata"] = new_metadata

        enriched = article.model_copy(update=updates)
        logger.debug(
            "ContentEnricher: id=%s tags=%d entities=%d reading_time=%s",
            article.id,
            len(new_tags),
            len(new_entities),
            new_extra.get("reading_time_seconds"),
        )
        return enriched

    def enrich_batch(self, articles: List[Article]) -> List[Article]:
        """Enrich a list of articles.

        Parameters
        ----------
        articles:
            Source articles.

        Returns
        -------
        List of enriched Article copies.
        """
        result = [self.enrich_article(a) for a in articles]
        logger.info("ContentEnricher.enrich_batch: processed=%d", len(result))
        return result
