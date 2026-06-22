"""Robots.txt Validator — section 4.4.

Respects the robots.txt exclusion standard using Python's built-in
``urllib.robotparser``.  Parsed files are cached in-memory to avoid
redundant network fetches during a single session.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = "HajeenBot/1.0"
_DEFAULT_CACHE_TTL: float = 3600.0  # seconds


class _CacheEntry:
    """Holds a parsed :class:`RobotFileParser` and its expiry timestamp."""

    __slots__ = ("parser", "expires_at")

    def __init__(self, parser: RobotFileParser, ttl: float) -> None:
        self.parser = parser
        self.expires_at: float = time.monotonic() + ttl


class RobotsChecker:
    """Async wrapper around :class:`urllib.robotparser.RobotFileParser`.

    Parameters
    ----------
    user_agent:
        The user-agent string used for ``can_fetch`` look-ups.
    cache_ttl:
        How long (in seconds) a parsed robots.txt file is cached in memory.
    """

    def __init__(
        self,
        user_agent: str = _DEFAULT_USER_AGENT,
        cache_ttl: float = _DEFAULT_CACHE_TTL,
    ) -> None:
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, _CacheEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def can_fetch(self, url: str) -> bool:
        """Return ``True`` when the robots.txt for *url* allows crawling.

        Parameters
        ----------
        url:
            The target URL to check.

        Returns
        -------
        ``True`` if fetching is allowed (or robots.txt is unreachable),
        ``False`` if explicitly disallowed.
        """
        parser = await self._get_parser(url)
        if parser is None:
            logger.debug("can_fetch: no parser (assume allowed) url=%s", url)
            return True

        allowed = parser.can_fetch(self.user_agent, url)
        logger.debug(
            "can_fetch: url=%s agent=%s allowed=%s",
            url,
            self.user_agent,
            allowed,
        )
        return allowed

    async def get_crawl_delay(self, url: str) -> Optional[float]:
        """Return the ``Crawl-delay`` directive for *url*, or ``None``.

        Parameters
        ----------
        url:
            Any URL under the target host.

        Returns
        -------
        Crawl delay in seconds, or ``None`` if not specified.
        """
        parser = await self._get_parser(url)
        if parser is None:
            return None

        delay = parser.crawl_delay(self.user_agent)
        logger.debug("get_crawl_delay: url=%s delay=%s", url, delay)
        return float(delay) if delay is not None else None

    def invalidate(self, host: str) -> None:
        """Remove the cached robots.txt entry for *host*.

        Parameters
        ----------
        host:
            Hostname (e.g. ``"example.com"``) whose cache entry to drop.
        """
        if host in self._cache:
            del self._cache[host]
            logger.debug("invalidate: cleared cache host=%s", host)

    def clear_cache(self) -> None:
        """Purge all cached robots.txt entries."""
        self._cache.clear()
        logger.debug("clear_cache: all entries removed")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_parser(self, url: str) -> Optional[RobotFileParser]:
        """Return a (possibly cached) :class:`RobotFileParser` for *url*."""
        robots_url = _robots_url(url)
        if robots_url is None:
            return None

        host = _host(url)
        if host is None:
            return None

        entry = self._cache.get(host)
        if entry is not None and time.monotonic() < entry.expires_at:
            logger.debug("_get_parser: cache hit host=%s", host)
            return entry.parser

        parser = await self._fetch_and_parse(robots_url)
        if parser is not None:
            self._cache[host] = _CacheEntry(parser, self.cache_ttl)

        return parser

    @staticmethod
    async def _fetch_and_parse(robots_url: str) -> Optional[RobotFileParser]:
        """Fetch and parse *robots_url* in a thread pool to stay non-blocking."""

        def _sync_parse() -> Optional[RobotFileParser]:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                logger.info("_fetch_and_parse: loaded url=%s", robots_url)
                return rp
            except Exception as exc:
                logger.warning(
                    "_fetch_and_parse: failed url=%s error=%s", robots_url, exc
                )
                return None

        return await asyncio.to_thread(_sync_parse)


# ---------------------------------------------------------------------------
# Module-level convenience functions (used by channel classes)
# ---------------------------------------------------------------------------

_default_checker: Optional[RobotsChecker] = None


def _get_default_checker() -> RobotsChecker:
    global _default_checker
    if _default_checker is None:
        _default_checker = RobotsChecker()
    return _default_checker


async def can_fetch(url: str, user_agent: str = _DEFAULT_USER_AGENT) -> bool:
    """Module-level helper: check whether crawling *url* is allowed.

    Uses a shared :class:`RobotsChecker` instance with default settings.

    Parameters
    ----------
    url:
        The URL to check.
    user_agent:
        User-agent string (defaults to ``HajeenBot/1.0``).

    Returns
    -------
    ``True`` if allowed, ``False`` if disallowed.
    """
    checker = _get_default_checker()
    checker.user_agent = user_agent
    return await checker.can_fetch(url)


async def get_crawl_delay(
    url: str, user_agent: str = _DEFAULT_USER_AGENT
) -> Optional[float]:
    """Module-level helper: retrieve the crawl-delay for *url*.

    Parameters
    ----------
    url:
        Any URL under the target host.
    user_agent:
        User-agent string (defaults to ``HajeenBot/1.0``).

    Returns
    -------
    Delay in seconds, or ``None`` if not declared.
    """
    checker = _get_default_checker()
    checker.user_agent = user_agent
    return await checker.get_crawl_delay(url)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _robots_url(url: str) -> Optional[str]:
    """Derive the robots.txt URL from any URL under the same host."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    except Exception:
        return None


def _host(url: str) -> Optional[str]:
    """Extract just the netloc (host[:port]) from a URL."""
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None
