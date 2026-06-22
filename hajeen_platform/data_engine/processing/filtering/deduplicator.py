"""Deduplicator — section 5.4.

Detects and removes duplicate articles using:
- Exact content hash (SHA-256 of normalised title + content)
- URL-based deduplication
- Fuzzy content similarity via difflib (no ML)

All state is in-memory (per-run or persistent across runs).
"""

from __future__ import annotations

import difflib
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class DeduplicatorConfig:
    """Controls deduplication behaviour."""

    deduplicate_urls: bool = True
    deduplicate_exact_content: bool = True
    deduplicate_similar_content: bool = False
    similarity_threshold: float = 0.85
    title_weight: float = 0.4
    content_preview_length: int = 500
    min_content_length: int = 20
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------

def _normalise_for_hash(text: str) -> str:
    """Normalise text for hashing (lowercase, collapse whitespace)."""
    import re
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def content_hash(article: Article, preview_length: int = 500) -> str:
    """Compute a SHA-256 hash of the article's title + content.

    Parameters
    ----------
    article:
        Article to hash.
    preview_length:
        Number of content characters to include in the hash.

    Returns
    -------
    Hex digest string.
    """
    title_key = _normalise_for_hash(article.title)
    content_key = _normalise_for_hash(article.content[:preview_length])
    key = f"{title_key}\n{content_key}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def url_hash(article: Article) -> str:
    """SHA-256 of the normalised article URL.

    Parameters
    ----------
    article:
        Article to hash.

    Returns
    -------
    Hex digest string.
    """
    url = str(article.url).strip().lower().rstrip("/")
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def similarity_score(a: Article, b: Article, preview_length: int = 500) -> float:
    """Compute similarity between two articles using difflib.

    Combines title similarity (weight 0.4) and content similarity (weight 0.6).

    Parameters
    ----------
    a:
        First article.
    b:
        Second article.
    preview_length:
        Characters of content to compare.

    Returns
    -------
    Float in [0.0, 1.0].
    """
    title_sim = difflib.SequenceMatcher(
        None,
        _normalise_for_hash(a.title),
        _normalise_for_hash(b.title),
    ).ratio()

    content_a = _normalise_for_hash(a.content[:preview_length])
    content_b = _normalise_for_hash(b.content[:preview_length])
    content_sim = difflib.SequenceMatcher(None, content_a, content_b).ratio()

    return 0.4 * title_sim + 0.6 * content_sim


# ---------------------------------------------------------------------------
# Dedup result
# ---------------------------------------------------------------------------

@dataclass
class DedupResult:
    """Result of a deduplication pass."""

    unique_articles: List[Article] = field(default_factory=list)
    duplicate_ids: List[str] = field(default_factory=list)
    similarity_pairs: List[Tuple[str, str, float]] = field(default_factory=list)

    @property
    def unique_count(self) -> int:
        return len(self.unique_articles)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_ids)


# ---------------------------------------------------------------------------
# Deduplicator
# ---------------------------------------------------------------------------

class Deduplicator:
    """Removes duplicate articles from a batch.

    State (seen hashes) persists across calls unless :meth:`reset` is called.
    This allows deduplication across multiple fetch cycles.

    Parameters
    ----------
    config:
        :class:`DeduplicatorConfig` controlling behaviour.
    """

    def __init__(self, config: Optional[DeduplicatorConfig] = None) -> None:
        self.config = config or DeduplicatorConfig()
        self._seen_url_hashes: Set[str] = set()
        self._seen_content_hashes: Set[str] = set()

    def reset(self) -> None:
        """Clear all seen hashes (start fresh dedup state)."""
        self._seen_url_hashes.clear()
        self._seen_content_hashes.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deduplicate(
        self,
        articles: List[Article],
        reset: bool = False,
    ) -> DedupResult:
        """Remove duplicates from *articles*.

        Parameters
        ----------
        articles:
            Input articles.
        reset:
            If ``True`` clear state before processing.

        Returns
        -------
        :class:`DedupResult` with unique articles and duplicate IDs.
        """
        if reset:
            self.reset()

        cfg = self.config
        unique: List[Article] = []
        dup_ids: List[str] = []

        for article in articles:
            if len(article.content.strip()) < cfg.min_content_length:
                unique.append(article)
                continue

            reason = self._is_duplicate(article, update_state=True)
            if reason:
                dup_ids.append(article.id)
                logger.debug("Deduplicator: dup id=%s reason=%s", article.id, reason)
            else:
                unique.append(article)

        result = DedupResult(
            unique_articles=unique,
            duplicate_ids=dup_ids,
        )

        if cfg.deduplicate_similar_content:
            result = self._fuzzy_dedup(result)

        logger.info(
            "Deduplicator: in=%d unique=%d duplicates=%d",
            len(articles),
            result.unique_count,
            result.duplicate_count,
        )
        return result

    def is_duplicate(self, article: Article) -> bool:
        """Stateless duplicate check (does NOT update seen sets).

        Parameters
        ----------
        article:
            Article to check.

        Returns
        -------
        ``True`` if the article is detected as a duplicate.
        """
        return self._is_duplicate(article, update_state=False) is not None

    def duplicate_score(self, a: Article, b: Article) -> float:
        """Compute a similarity/duplicate score between two articles.

        Parameters
        ----------
        a:
            First article.
        b:
            Second article.

        Returns
        -------
        Float in [0.0, 1.0]; 1.0 = identical.
        """
        if str(a.url) == str(b.url):
            return 1.0
        if content_hash(a) == content_hash(b):
            return 1.0
        return similarity_score(a, b, self.config.content_preview_length)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_duplicate(
        self, article: Article, update_state: bool = True
    ) -> Optional[str]:
        """Return a rejection reason string or None if not a duplicate."""
        cfg = self.config

        if cfg.deduplicate_urls:
            uh = url_hash(article)
            if uh in self._seen_url_hashes:
                return "duplicate_url"
            if update_state:
                self._seen_url_hashes.add(uh)

        if cfg.deduplicate_exact_content:
            ch = content_hash(article, cfg.content_preview_length)
            if ch in self._seen_content_hashes:
                return "duplicate_content"
            if update_state:
                self._seen_content_hashes.add(ch)

        return None

    def _fuzzy_dedup(self, result: DedupResult) -> DedupResult:
        """Apply fuzzy similarity check to the already URL/hash-deduped list."""
        threshold = self.config.similarity_threshold
        articles = result.unique_articles
        keep: List[Article] = []
        extra_dups: List[str] = list(result.duplicate_ids)
        pairs: List[Tuple[str, str, float]] = list(result.similarity_pairs)
        dup_set: Set[str] = set(result.duplicate_ids)

        for i, a in enumerate(articles):
            if a.id in dup_set:
                continue
            is_dup = False
            for j in range(i):
                if articles[j].id in dup_set:
                    continue
                score = similarity_score(
                    a, articles[j], self.config.content_preview_length
                )
                if score >= threshold:
                    pairs.append((articles[j].id, a.id, score))
                    extra_dups.append(a.id)
                    dup_set.add(a.id)
                    is_dup = True
                    break
            if not is_dup:
                keep.append(a)

        return DedupResult(
            unique_articles=keep,
            duplicate_ids=extra_dups,
            similarity_pairs=pairs,
        )
