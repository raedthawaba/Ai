"""Content Filter — section 4.11.

Filters articles based on configurable quality, language, keyword, and
duplicate criteria.  All checks are pure Python (no ML dependencies).

Capabilities:
- Minimum content / title length checks
- Language detection via character-set heuristics (Arabic vs English)
- Keyword allowlist / blocklist (title + content)
- Duplicate URL deduplication within a batch
- Quality scoring with configurable threshold
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Arabic / Latin character ranges for language detection
# ---------------------------------------------------------------------------

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_RE = re.compile(r"[a-zA-Z]")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FilterConfig:
    """Controls what :class:`ContentFilter` keeps and rejects."""

    min_title_length: int = 5
    min_content_length: int = 20
    max_content_length: Optional[int] = None
    allowed_languages: List[str] = field(default_factory=list)
    blocked_keywords: List[str] = field(default_factory=list)
    required_keywords: List[str] = field(default_factory=list)
    deduplicate_urls: bool = True
    deduplicate_content: bool = False
    min_quality_score: float = 0.0
    keyword_case_sensitive: bool = False


# ---------------------------------------------------------------------------
# Language detection helpers
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """Detect the dominant language of *text* using character-set heuristics.

    Returns ``"ar"`` when Arabic characters dominate, ``"en"`` when Latin
    characters dominate, or ``"unknown"`` otherwise.

    Parameters
    ----------
    text:
        Input text to analyse.

    Returns
    -------
    Two-letter language code or ``"unknown"``.
    """
    if not text:
        return "unknown"

    arabic_chars = len(_ARABIC_RE.findall(text))
    latin_chars = len(_LATIN_RE.findall(text))
    total = arabic_chars + latin_chars

    if total == 0:
        return "unknown"

    arabic_ratio = arabic_chars / total
    if arabic_ratio >= 0.5:
        return "ar"
    return "en"


def is_arabic(text: str) -> bool:
    """Return ``True`` when Arabic characters make up ≥ 50 % of alphabetic chars."""
    return detect_language(text) == "ar"


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def compute_quality_score(article: Article) -> float:
    """Compute a simple quality score in [0.0, 1.0].

    Scoring criteria:
    - Content length (longer is better, up to ~1000 chars → 0.4 pts)
    - Title length (up to ~80 chars → 0.2 pts)
    - Has summary (+0.1)
    - Has author (+0.1)
    - Has tags (+0.1)
    - URL present (always True for valid articles → +0.1)

    Parameters
    ----------
    article:
        Article to score.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    score = 0.0

    content_len = len(article.content.strip())
    score += min(content_len / 1000, 1.0) * 0.4

    title_len = len(article.title.strip())
    score += min(title_len / 80, 1.0) * 0.2

    if article.summary:
        score += 0.1
    if article.metadata.author:
        score += 0.1
    if article.metadata.tags:
        score += 0.1
    if article.url:
        score += 0.1

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Filter result
# ---------------------------------------------------------------------------

@dataclass
class FilterResult:
    """Result of a batch filtering pass."""

    kept: List[Article] = field(default_factory=list)
    rejected: List[Article] = field(default_factory=list)
    rejection_reasons: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.kept) + len(self.rejected)

    @property
    def keep_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return len(self.kept) / self.total


# ---------------------------------------------------------------------------
# ContentFilter
# ---------------------------------------------------------------------------

class ContentFilter:
    """Filters batches of articles according to :class:`FilterConfig`.

    Parameters
    ----------
    config:
        Filter configuration.  Defaults to permissive settings (keep all).
    """

    def __init__(self, config: Optional[FilterConfig] = None) -> None:
        self.config = config or FilterConfig()
        self._seen_urls: Set[str] = set()
        self._seen_content_hashes: Set[str] = set()

    def reset(self) -> None:
        """Clear deduplication state (seen URLs and content hashes)."""
        self._seen_urls.clear()
        self._seen_content_hashes.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter_batch(
        self,
        articles: List[Article],
        reset_dedup: bool = False,
    ) -> FilterResult:
        """Apply all configured filters to a list of articles.

        Parameters
        ----------
        articles:
            Input articles to filter.
        reset_dedup:
            If ``True`` clear deduplication state before filtering.

        Returns
        -------
        :class:`FilterResult` with ``kept`` and ``rejected`` lists.
        """
        if reset_dedup:
            self.reset()

        result = FilterResult()
        for article in articles:
            reason = self._check(article)
            if reason is None:
                result.kept.append(article)
            else:
                result.rejected.append(article)
                result.rejection_reasons[article.id] = reason
                logger.debug(
                    "ContentFilter: rejected id=%s reason=%s", article.id, reason
                )

        logger.info(
            "ContentFilter.filter_batch: total=%d kept=%d rejected=%d",
            result.total,
            len(result.kept),
            len(result.rejected),
        )
        return result

    def is_allowed(self, article: Article) -> bool:
        """Return ``True`` when *article* passes all filters (stateless check).

        Note: does NOT update deduplication state.

        Parameters
        ----------
        article:
            Article to evaluate.
        """
        return self._check(article, update_state=False) is None

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check(
        self, article: Article, update_state: bool = True
    ) -> Optional[str]:
        """Run all checks; return rejection reason string or ``None`` if OK."""

        if len(article.title.strip()) < self.config.min_title_length:
            return f"title_too_short ({len(article.title.strip())} < {self.config.min_title_length})"

        if len(article.content.strip()) < self.config.min_content_length:
            return f"content_too_short ({len(article.content.strip())} < {self.config.min_content_length})"

        if (
            self.config.max_content_length
            and len(article.content) > self.config.max_content_length
        ):
            return f"content_too_long ({len(article.content)} > {self.config.max_content_length})"

        if self.config.allowed_languages:
            lang = article.metadata.language or detect_language(
                article.title + " " + article.content
            )
            if lang not in self.config.allowed_languages:
                return f"language_not_allowed ({lang!r} not in {self.config.allowed_languages})"

        if self.config.blocked_keywords:
            combined = article.title + " " + article.content
            if not self.config.keyword_case_sensitive:
                combined = combined.lower()
            for kw in self.config.blocked_keywords:
                needle = kw if self.config.keyword_case_sensitive else kw.lower()
                if needle in combined:
                    return f"blocked_keyword ({kw!r})"

        if self.config.required_keywords:
            combined = article.title + " " + article.content
            if not self.config.keyword_case_sensitive:
                combined = combined.lower()
            found = any(
                (kw if self.config.keyword_case_sensitive else kw.lower()) in combined
                for kw in self.config.required_keywords
            )
            if not found:
                return "required_keyword_missing"

        if self.config.min_quality_score > 0:
            score = compute_quality_score(article)
            if score < self.config.min_quality_score:
                return f"quality_too_low ({score:.4f} < {self.config.min_quality_score})"

        url_key = str(article.url)
        if self.config.deduplicate_urls:
            if url_key in self._seen_urls:
                return "duplicate_url"
            if update_state:
                self._seen_urls.add(url_key)

        if self.config.deduplicate_content:
            content_hash = _content_hash(article)
            if content_hash in self._seen_content_hashes:
                return "duplicate_content"
            if update_state:
                self._seen_content_hashes.add(content_hash)

        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(article: Article) -> str:
    """SHA-256 of normalised title + first 500 chars of content."""
    key = (article.title.strip().lower() + article.content.strip()[:500].lower())
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
