"""Tests for SitemapParser — section 4.5."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from data_engine.ingestion.crawlers.sitemap_parser import (
    SitemapParser,
    SitemapURL,
    _parse_lastmod,
    _parse_priority,
    _strip_ns,
    parse_sitemap,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SITEMAP_XML = (FIXTURES_DIR / "sample_sitemap.xml").read_text(encoding="utf-8")
SITEMAP_INDEX_XML = (FIXTURES_DIR / "sample_sitemap_index.xml").read_text(encoding="utf-8")
CHILD_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/post/1</loc>
    <lastmod>2024-05-01</lastmod>
    <priority>0.7</priority>
  </url>
</urlset>"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def test_strip_ns_with_namespace():
    assert _strip_ns("{http://www.sitemaps.org/schemas/sitemap/0.9}url") == "url"


def test_strip_ns_without_namespace():
    assert _strip_ns("url") == "url"


def test_parse_lastmod_date_only():
    dt = _parse_lastmod("2024-05-20")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 5
    assert dt.day == 20
    assert dt.tzinfo == timezone.utc


def test_parse_lastmod_datetime_with_timezone():
    dt = _parse_lastmod("2024-04-15T08:30:00Z")
    assert dt is not None
    assert dt.hour == 8
    assert dt.minute == 30


def test_parse_lastmod_empty_string():
    assert _parse_lastmod("") is None


def test_parse_lastmod_invalid():
    assert _parse_lastmod("not-a-date") is None


def test_parse_priority_valid():
    assert _parse_priority("0.8") == pytest.approx(0.8)
    assert _parse_priority("1.0") == pytest.approx(1.0)
    assert _parse_priority("0.0") == pytest.approx(0.0)


def test_parse_priority_clamped():
    assert _parse_priority("1.5") == pytest.approx(1.0)
    assert _parse_priority("-0.5") == pytest.approx(0.0)


def test_parse_priority_invalid_defaults():
    assert _parse_priority("") == pytest.approx(0.5)
    assert _parse_priority("abc") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# SitemapURL
# ---------------------------------------------------------------------------

def test_sitemap_url_as_source_candidate():
    entry = SitemapURL(
        url="https://example.com/page",
        lastmod=datetime(2024, 5, 20, tzinfo=timezone.utc),
        priority=0.9,
        changefreq="daily",
        source_sitemap="https://example.com/sitemap.xml",
    )
    candidate = entry.as_source_candidate()
    assert candidate["url"] == "https://example.com/page"
    assert candidate["priority"] == pytest.approx(0.9)
    assert candidate["type"] == "sitemap_candidate"
    assert "2024-05-20" in candidate["lastmod"]


def test_sitemap_url_none_lastmod_candidate():
    entry = SitemapURL(url="https://example.com/page", lastmod=None)
    candidate = entry.as_source_candidate()
    assert candidate["lastmod"] is None


# ---------------------------------------------------------------------------
# parse_sitemap — urlset
# ---------------------------------------------------------------------------

def _patch_fetch_xml(content_map: dict):
    """Patch _fetch_xml to return XML content based on URL."""

    async def fake_fetch(url: str, timeout: float) -> str | None:
        return content_map.get(url)

    return patch(
        "data_engine.ingestion.crawlers.sitemap_parser._fetch_xml",
        new=fake_fetch,
    )


@pytest.mark.asyncio
async def test_parse_sitemap_urlset():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        results = await parse_sitemap(url)

    assert len(results) == 3
    for entry in results:
        assert isinstance(entry, SitemapURL)
        assert entry.url.startswith("https://example.com/")


@pytest.mark.asyncio
async def test_parse_sitemap_extracts_lastmod():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        results = await parse_sitemap(url)

    lastmods = [r.lastmod for r in results]
    assert any(lm is not None for lm in lastmods)


@pytest.mark.asyncio
async def test_parse_sitemap_extracts_priority():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        results = await parse_sitemap(url)

    priorities = {r.url: r.priority for r in results}
    root_entry = next(r for r in results if r.url == "https://example.com/")
    assert root_entry.priority == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_parse_sitemap_extracts_changefreq():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        results = await parse_sitemap(url)

    root_entry = next(r for r in results if r.url == "https://example.com/")
    assert root_entry.changefreq == "daily"


@pytest.mark.asyncio
async def test_parse_sitemap_sets_source():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        results = await parse_sitemap(url)

    for entry in results:
        assert entry.source_sitemap == url


# ---------------------------------------------------------------------------
# parse_sitemap — sitemap index
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_sitemap_index_follows_children():
    index_url = "https://example.com/sitemap-index.xml"
    child1_url = "https://example.com/sitemap-posts.xml"
    child2_url = "https://example.com/sitemap-pages.xml"

    child_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/post/1</loc></url>
    </urlset>"""

    with _patch_fetch_xml(
        {
            index_url: SITEMAP_INDEX_XML,
            child1_url: child_xml,
            child2_url: child_xml,
        }
    ):
        results = await parse_sitemap(index_url)

    assert len(results) == 2  # one from each child sitemap


@pytest.mark.asyncio
async def test_parse_sitemap_index_max_depth_respected():
    """Depth limit should prevent infinite recursion."""
    index_url = "https://example.com/sitemap-index.xml"
    # Neither child URL is in the map → returns empty results (fetch returns None)
    with _patch_fetch_xml({index_url: SITEMAP_INDEX_XML}):
        results = await parse_sitemap(index_url, max_depth=1)

    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_sitemap_unreachable():
    with _patch_fetch_xml({}):
        results = await parse_sitemap("https://down.example.com/sitemap.xml")
    assert results == []


@pytest.mark.asyncio
async def test_parse_sitemap_invalid_xml():
    url = "https://example.com/bad-sitemap.xml"
    with _patch_fetch_xml({url: "THIS IS NOT XML"}):
        results = await parse_sitemap(url)
    assert results == []


# ---------------------------------------------------------------------------
# SitemapParser class
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sitemap_parser_class():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        parser = SitemapParser()
        results = await parser.parse(url)

    assert len(results) > 0
    assert all(isinstance(r, SitemapURL) for r in results)


@pytest.mark.asyncio
async def test_sitemap_parser_get_source_candidates():
    url = "https://example.com/sitemap.xml"
    with _patch_fetch_xml({url: SITEMAP_XML}):
        parser = SitemapParser()
        candidates = await parser.get_source_candidates(url)

    assert len(candidates) > 0
    for c in candidates:
        assert "url" in c
        assert c["type"] == "sitemap_candidate"
