"""Quality Scorer — section 5.6.

Scores articles on multiple quality dimensions and provides a rejection
decision based on a configurable threshold.

Scoring dimensions:
- Content length (chars)
- Word count
- Link/URL density
- Repetition ratio (consecutive repeated words)
- Simple readability (avg sentence length)
- Author / tags / summary bonus
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?؟])\s+")
_ARABIC_WORD_RE = re.compile(r"[\u0600-\u06FF]{2,}", re.UNICODE)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class QualityScorerConfig:
    """Controls quality scoring behaviour."""

    min_words: int = 20
    min_chars: int = 50
    max_link_density: float = 0.3
    max_repetition_ratio: float = 0.5
    max_avg_sentence_length: int = 200
    threshold: float = 0.4
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "content_length": 0.25,
            "word_count": 0.20,
            "link_density": 0.15,
            "repetition": 0.15,
            "readability": 0.10,
            "metadata": 0.15,
        }
    )
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Individual scoring functions
# ---------------------------------------------------------------------------

def score_content_length(text: str, min_chars: int = 50) -> float:
    """Score based on character count.

    Returns 0 when below *min_chars*, scales to 1 at ~2000 chars.

    Parameters
    ----------
    text:
        Article content.
    min_chars:
        Minimum acceptable length.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    n = len(text.strip())
    if n < min_chars:
        return 0.0
    return min(n / 2000, 1.0)


def score_word_count(text: str, min_words: int = 20) -> float:
    """Score based on word count.

    Parameters
    ----------
    text:
        Article content.
    min_words:
        Minimum acceptable word count.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    words = _WORD_RE.findall(text)
    n = len(words)
    if n < min_words:
        return 0.0
    return min(n / 300, 1.0)


def score_link_density(text: str, max_density: float = 0.3) -> float:
    """Score based on URL density (lower density = higher score).

    Parameters
    ----------
    text:
        Article content.
    max_density:
        Density above which the score is 0.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    if not text:
        return 1.0
    urls = _URL_RE.findall(text)
    words = _WORD_RE.findall(text)
    if not words:
        return 1.0
    density = len(urls) / (len(words) + 1)
    if density >= max_density:
        return 0.0
    return 1.0 - (density / max_density)


def score_repetition(text: str, max_ratio: float = 0.5) -> float:
    """Score based on repetition of consecutive word pairs.

    High repetition (spam-like) yields a low score.

    Parameters
    ----------
    text:
        Article content.
    max_ratio:
        Repetition ratio above which score is 0.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if len(words) < 4:
        return 1.0

    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    unique_bigrams = len(set(bigrams))
    total_bigrams = len(bigrams)

    repetition = 1.0 - (unique_bigrams / total_bigrams)
    if repetition >= max_ratio:
        return 0.0
    return 1.0 - (repetition / max_ratio)


def score_readability(text: str, max_avg_len: int = 200) -> float:
    """Score based on average sentence length (shorter = more readable).

    Parameters
    ----------
    text:
        Article content.
    max_avg_len:
        Maximum acceptable average sentence length in chars.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    if not sentences:
        return 0.5
    avg_len = sum(len(s) for s in sentences) / len(sentences)
    if avg_len >= max_avg_len:
        return 0.0
    return 1.0 - (avg_len / max_avg_len)


def score_metadata(article: Article) -> float:
    """Score bonus from metadata completeness.

    Parameters
    ----------
    article:
        Article to evaluate.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    score = 0.0
    if article.metadata.author:
        score += 0.3
    if article.metadata.tags:
        score += 0.3
    if article.summary:
        score += 0.2
    if article.metadata.language and article.metadata.language != "unknown":
        score += 0.2
    return score


# ---------------------------------------------------------------------------
# Quality score result
# ---------------------------------------------------------------------------

@dataclass
class QualityScore:
    """Detailed quality score for a single article."""

    article_id: str
    total_score: float
    passes: bool
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    rejection_reason: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"QualityScore(id={self.article_id!r} "
            f"score={self.total_score:.3f} "
            f"passes={self.passes})"
        )


# ---------------------------------------------------------------------------
# QualityScorer
# ---------------------------------------------------------------------------

class QualityScorer:
    """Computes quality scores and filters low-quality articles.

    Parameters
    ----------
    config:
        :class:`QualityScorerConfig`.
    """

    def __init__(self, config: Optional[QualityScorerConfig] = None) -> None:
        self.config = config or QualityScorerConfig()

    def score_article(self, article: Article) -> QualityScore:
        """Compute a detailed quality score for *article*.

        Parameters
        ----------
        article:
            Article to score.

        Returns
        -------
        :class:`QualityScore`.
        """
        cfg = self.config
        w = cfg.weights
        content = article.content

        dims: Dict[str, float] = {
            "content_length": score_content_length(content, cfg.min_chars),
            "word_count": score_word_count(content, cfg.min_words),
            "link_density": score_link_density(content, cfg.max_link_density),
            "repetition": score_repetition(content, cfg.max_repetition_ratio),
            "readability": score_readability(content, cfg.max_avg_sentence_length),
            "metadata": score_metadata(article),
        }

        total = sum(dims.get(k, 0.0) * v for k, v in w.items())
        total = round(min(total, 1.0), 4)
        passes = total >= cfg.threshold

        rejection_reason: Optional[str] = None
        if not passes:
            worst_dim = min(dims, key=dims.get)
            rejection_reason = f"quality_below_threshold (score={total:.3f}, worst={worst_dim})"

        return QualityScore(
            article_id=article.id,
            total_score=total,
            passes=passes,
            dimension_scores=dims,
            rejection_reason=rejection_reason,
        )

    def filter_batch(
        self, articles: List[Article]
    ) -> Tuple[List[Article], List[QualityScore]]:
        """Score and filter *articles*.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        Tuple of ``(kept_articles, all_scores)``.
        """
        kept: List[Article] = []
        all_scores: List[QualityScore] = []

        for article in articles:
            score = self.score_article(article)
            all_scores.append(score)
            if score.passes:
                kept.append(article)
            else:
                logger.debug(
                    "QualityScorer: rejected id=%s score=%.3f reason=%s",
                    article.id,
                    score.total_score,
                    score.rejection_reason,
                )

        logger.info(
            "QualityScorer.filter_batch: in=%d kept=%d rejected=%d",
            len(articles),
            len(kept),
            len(articles) - len(kept),
        )
        return kept, all_scores

    def score_batch(self, articles: List[Article]) -> List[QualityScore]:
        """Score all articles without filtering.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of :class:`QualityScore` objects.
        """
        return [self.score_article(a) for a in articles]
