"""Sitemap Parser — section 4.5.

Reads standard XML sitemaps and sitemap index files, extracts URLs with
their ``lastmod`` and ``priority`` values, and returns them as
*source candidate* dictionaries ready for ingestion scheduling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# XML namespaces used by the Sitemaps Protocol
_NS_SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Maximum depth when recursively resolving sitemap indexes
_MAX_DEPTH = 3


@dataclass
class SitemapURL:
    """A single URL entry extracted from a sitemap."""

    url: str
    lastmod: Optional[datetime] = None
    priority: float = 0.5
    changefreq: Optional[str] = None
    source_sitemap: str = ""

    def as_source_candidate(self) -> dict:
        """Convert to a source candidate dict for use by ingestion schedulers."""
        return {
            "url": self.url,
            "lastmod": self.lastmod.isoformat() if self.lastmod else None,
            "priority": self.priority,
            "changefreq": self.changefreq,
            "source_sitemap": self.source_sitemap,
            "type": "sitemap_candidate",
        }


class SitemapParser:
    """Async sitemap parser supporting sitemap.xml and sitemap index files.

    Parameters
    ----------
    max_depth:
        Maximum recursion depth when following sitemap index files.
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        max_depth: int = _MAX_DEPTH,
        timeout: float = 15.0,
    ) -> None:
        self.max_depth = max_depth
        self.timeout = timeout

    async def parse(self, sitemap_url: str) -> List[SitemapURL]:
        """Fetch and parse a sitemap URL, following indexes recursively.

        Parameters
        ----------
        sitemap_url:
            URL of the ``sitemap.xml`` or sitemap index to parse.

        Returns
        -------
        Flat list of :class:`SitemapURL` objects.
        """
        return await parse_sitemap(
            sitemap_url, max_depth=self.max_depth, timeout=self.timeout
        )

    async def get_source_candidates(self, sitemap_url: str) -> List[dict]:
        """Return a list of source candidate dicts from *sitemap_url*."""
        entries = await self.parse(sitemap_url)
        return [e.as_source_candidate() for e in entries]


# ---------------------------------------------------------------------------
# Module-level helper (used by channel classes directly)
# ---------------------------------------------------------------------------

async def parse_sitemap(
    sitemap_url: str,
    max_depth: int = _MAX_DEPTH,
    timeout: float = 15.0,
) -> List[SitemapURL]:
    """Fetch and parse a sitemap or sitemap index, returning all URLs found.

    Parameters
    ----------
    sitemap_url:
        URL of the sitemap to parse (can be a sitemap index).
    max_depth:
        Maximum depth for recursive sitemap index resolution.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    Flat list of :class:`SitemapURL` objects.
    """
    logger.info("parse_sitemap: starting url=%s depth_limit=%d", sitemap_url, max_depth)
    results: List[SitemapURL] = []
    await _recursive_parse(sitemap_url, results, depth=0, max_depth=max_depth, timeout=timeout)
    logger.info("parse_sitemap: done url=%s total_urls=%d", sitemap_url, len(results))
    return results


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

async def _fetch_xml(url: str, timeout: float) -> Optional[str]:
    """Fetch raw XML text from *url* asynchronously."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "HajeenBot/1.0 (sitemap reader)"},
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.text
    except Exception as exc:
        logger.warning("_fetch_xml: failed url=%s error=%s", url, exc)
        return None


async def _recursive_parse(
    sitemap_url: str,
    results: List[SitemapURL],
    depth: int,
    max_depth: int,
    timeout: float,
) -> None:
    """Recursively fetch and parse sitemaps (indexes are followed)."""
    if depth > max_depth:
        logger.warning("_recursive_parse: max depth reached url=%s", sitemap_url)
        return

    xml_text = await _fetch_xml(sitemap_url, timeout)
    if xml_text is None:
        return

    try:
        root = await asyncio.to_thread(ET.fromstring, xml_text)
    except ET.ParseError as exc:
        logger.error("_recursive_parse: XML parse error url=%s error=%s", sitemap_url, exc)
        return

    # Strip the namespace prefix for easier tag matching
    tag = _strip_ns(root.tag)

    if tag == "sitemapindex":
        await _parse_sitemap_index(root, results, depth, max_depth, timeout)
    elif tag == "urlset":
        _parse_urlset(root, results, source=sitemap_url)
    else:
        logger.warning(
            "_recursive_parse: unknown root tag=%s url=%s", root.tag, sitemap_url
        )


async def _parse_sitemap_index(
    root: ET.Element,
    results: List[SitemapURL],
    depth: int,
    max_depth: int,
    timeout: float,
) -> None:
    """Parse a ``<sitemapindex>`` element and recurse into each child sitemap."""
    child_urls: List[str] = []

    for sitemap_el in root:
        if _strip_ns(sitemap_el.tag) != "sitemap":
            continue
        loc_el = _find_child(sitemap_el, "loc")
        if loc_el is not None and loc_el.text:
            child_urls.append(loc_el.text.strip())

    logger.debug(
        "_parse_sitemap_index: found %d child sitemaps depth=%d",
        len(child_urls),
        depth,
    )

    tasks = [
        _recursive_parse(u, results, depth + 1, max_depth, timeout)
        for u in child_urls
    ]
    await asyncio.gather(*tasks)


def _parse_urlset(
    root: ET.Element,
    results: List[SitemapURL],
    source: str,
) -> None:
    """Parse a ``<urlset>`` element and append :class:`SitemapURL` objects."""
    for url_el in root:
        if _strip_ns(url_el.tag) != "url":
            continue

        loc_el = _find_child(url_el, "loc")
        if loc_el is None or not (loc_el.text or "").strip():
            continue

        url_str = loc_el.text.strip()
        lastmod = _parse_lastmod(_child_text(url_el, "lastmod"))
        priority = _parse_priority(_child_text(url_el, "priority"))
        changefreq = _child_text(url_el, "changefreq") or None

        results.append(
            SitemapURL(
                url=url_str,
                lastmod=lastmod,
                priority=priority,
                changefreq=changefreq,
                source_sitemap=source,
            )
        )

    logger.debug(
        "_parse_urlset: extracted %d URLs source=%s", len(results), source
    )


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    """Remove the namespace URI from an XML tag string, e.g. ``{ns}url`` → ``url``."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _find_child(element: ET.Element, local_tag: str) -> Optional[ET.Element]:
    """Find a direct child element by local tag name (namespace-agnostic)."""
    for child in element:
        if _strip_ns(child.tag) == local_tag:
            return child
    return None


def _child_text(element: ET.Element, local_tag: str) -> str:
    """Return stripped text of a named child element, or empty string."""
    child = _find_child(element, local_tag)
    return (child.text or "").strip() if child is not None else ""


# ---------------------------------------------------------------------------
# Value parsers
# ---------------------------------------------------------------------------

def _parse_lastmod(raw: str) -> Optional[datetime]:
    """Parse a sitemap ``<lastmod>`` value to a timezone-aware datetime."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    logger.debug("_parse_lastmod: cannot parse raw=%r", raw)
    return None


def _parse_priority(raw: str) -> float:
    """Parse a sitemap ``<priority>`` value to a float in [0.0, 1.0]."""
    try:
        value = float(raw)
        return max(0.0, min(1.0, value))
    except (ValueError, TypeError):
        return 0.5
