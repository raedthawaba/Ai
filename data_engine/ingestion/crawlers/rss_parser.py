"""RSS / Atom Feed Parser — section 4.3.

Parses RSS and Atom feeds using *feedparser*, converts entries to
:class:`~shared.schemas.article.Article` objects and supports both
Arabic and English content.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from email.utils import parsedate_to_datetime

import feedparser

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_channel_id

logger = logging.getLogger(__name__)


class RSSParser:
    """Wrapper around *feedparser* that converts feed entries to Articles.

    Parameters
    ----------
    source_id:
        Identifier of the channel / source that owns the feed.
    default_language:
        ISO-639-1 code used when the feed does not declare a language.
        Defaults to ``"ar"`` (Arabic).
    """

    def __init__(
        self,
        source_id: str = "rss",
        default_language: str = "ar",
    ) -> None:
        self.source_id = source_id
        self.default_language = default_language

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, url: str) -> List[Article]:
        """Fetch and parse an RSS/Atom feed URL.

        Parameters
        ----------
        url:
            Full URL of the RSS or Atom feed.

        Returns
        -------
        List of :class:`Article` objects (may be empty on error).
        """
        return await parse_rss_feed(
            url,
            source_id=self.source_id,
            default_language=self.default_language,
        )

    async def validate(self, url: str) -> bool:
        """Check whether a URL points to a valid RSS/Atom feed."""
        return await validate_rss_feed(url)


# ---------------------------------------------------------------------------
# Module-level helpers (used by channel classes directly)
# ---------------------------------------------------------------------------

async def parse_rss_feed(
    url: str,
    source_id: str = "rss",
    default_language: str = "ar",
) -> List[Article]:
    """Fetch and parse an RSS or Atom feed and return Article objects.

    Supports both Arabic and English feeds.  Encoding and character-set
    issues are handled transparently by *feedparser*.

    Parameters
    ----------
    url:
        Full URL of the RSS or Atom feed.
    source_id:
        Channel / source identifier attached to every article's metadata.
    default_language:
        Fallback language code when the feed does not declare one.

    Returns
    -------
    List of :class:`Article` objects parsed from the feed entries.
    """
    import asyncio

    logger.info("parse_rss_feed: fetching url=%s", url)

    try:
        feed = await asyncio.to_thread(feedparser.parse, url)
    except Exception as exc:
        logger.error("parse_rss_feed: feedparser raised url=%s error=%s", url, exc)
        return []

    if feed.bozo and not feed.entries:
        logger.warning(
            "parse_rss_feed: bozo flag set and no entries url=%s exception=%s",
            url,
            feed.get("bozo_exception"),
        )
        return []

    language = _detect_feed_language(feed, default_language)
    articles: List[Article] = []

    for entry in feed.entries:
        article = _entry_to_article(entry, source_id=source_id, language=language)
        if article is not None:
            articles.append(article)

    logger.info(
        "parse_rss_feed: done url=%s entries=%d articles=%d",
        url,
        len(feed.entries),
        len(articles),
    )
    return articles


async def validate_rss_feed(url: str) -> bool:
    """Return ``True`` when the URL is a parseable RSS or Atom feed.

    Validation checks:
    - feedparser must not set the *bozo* flag (malformed XML).
    - The feed must contain at least one entry **or** declare a feed title.

    Parameters
    ----------
    url:
        Full URL to validate.

    Returns
    -------
    ``True`` if valid, ``False`` otherwise.
    """
    import asyncio

    try:
        feed = await asyncio.to_thread(feedparser.parse, url)
    except Exception as exc:
        logger.warning("validate_rss_feed: parse error url=%s error=%s", url, exc)
        return False

    if feed.bozo:
        bozo_exc = feed.get("bozo_exception")
        logger.warning(
            "validate_rss_feed: bozo flag url=%s exception=%s", url, bozo_exc
        )
        return False

    has_title = bool(feed.feed.get("title", "").strip())
    has_entries = len(feed.entries) > 0

    valid = has_title or has_entries
    logger.info("validate_rss_feed: url=%s valid=%s", url, valid)
    return valid


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_feed_language(feed: feedparser.FeedParserDict, default: str) -> str:
    """Extract the language declared in the feed or return *default*."""
    lang = (
        feed.feed.get("language", "")
        or feed.feed.get("dc_language", "")
    ).strip().lower()

    if lang:
        return lang[:2]
    return default


def _entry_to_article(
    entry: feedparser.FeedParserDict,
    source_id: str,
    language: str,
) -> Optional[Article]:
    """Convert a single feed entry to an :class:`Article`.

    Returns ``None`` when the entry is missing mandatory fields (title, link).
    """
    title = _get_text(entry, "title")
    link = _get_text(entry, "link")

    if not title or not link:
        logger.debug(
            "_entry_to_article: skipping entry missing title or link id=%s",
            entry.get("id", "?"),
        )
        return None

    content = _extract_content(entry)
    if not content:
        content = _get_text(entry, "summary") or title

    published_at = _parse_published(entry)
    author = _get_text(entry, "author") or _get_text(entry, "dc_creator")
    categories = _extract_categories(entry)

    try:
        return Article(
            id=_generate_article_id(link),
            title=title.strip(),
            content=content.strip(),
            url=link,  # type: ignore[arg-type]
            published_at=published_at,
            summary=_get_text(entry, "summary") or None,
            metadata=ArticleMetadata(
                source_id=source_id,
                author=author or None,
                language=language,
                tags=categories,
                extra={
                    "raw_id": entry.get("id", ""),
                    "feed_url": link,
                },
            ),
        )
    except Exception as exc:
        logger.warning("_entry_to_article: validation error entry=%s error=%s", link, exc)
        return None


def _get_text(entry: feedparser.FeedParserDict, key: str) -> str:
    """Safely retrieve a string value from a feed entry."""
    value = entry.get(key, "")
    if isinstance(value, list) and value:
        value = value[0].get("value", "") if isinstance(value[0], dict) else str(value[0])
    return str(value).strip() if value else ""


def _extract_content(entry: feedparser.FeedParserDict) -> str:
    """Extract the richest text content available from a feed entry."""
    content_list = entry.get("content", [])
    if content_list:
        for item in content_list:
            if isinstance(item, dict):
                text = item.get("value", "")
                if text:
                    return text

    full_text = entry.get("content_encoded", "") or entry.get("dc_description", "")
    return str(full_text).strip()


def _extract_categories(entry: feedparser.FeedParserDict) -> List[str]:
    """Extract category / tag strings from a feed entry."""
    tags_raw = entry.get("tags", [])
    categories: List[str] = []
    for tag in tags_raw:
        if isinstance(tag, dict):
            label = tag.get("label") or tag.get("term") or ""
            if label:
                categories.append(str(label).strip())
        elif isinstance(tag, str) and tag.strip():
            categories.append(tag.strip())
    return categories


def _parse_published(entry: feedparser.FeedParserDict) -> datetime:
    """Parse the publication date from a feed entry.

    Falls back to the current UTC time if no valid date is found.
    """
    for key in ("published", "updated", "dc_date", "created"):
        raw = entry.get(f"{key}_parsed") or entry.get(key, "")

        if hasattr(raw, "tm_year"):
            try:
                return datetime(
                    raw.tm_year,
                    raw.tm_mon,
                    raw.tm_mday,
                    raw.tm_hour,
                    raw.tm_min,
                    raw.tm_sec,
                    tzinfo=timezone.utc,
                )
            except (ValueError, OverflowError):
                pass

        if isinstance(raw, str) and raw.strip():
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass

    return datetime.now(tz=timezone.utc)


def _generate_article_id(url: str) -> str:
    """Generate a deterministic article ID based on the URL."""
    import hashlib

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"art_{digest}"
