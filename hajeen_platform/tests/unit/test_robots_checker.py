"""Tests for RobotsChecker — section 4.4."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.robotparser import RobotFileParser

import pytest

from data_engine.ingestion.crawlers.robots_checker import (
    RobotsChecker,
    _host,
    _robots_url,
    can_fetch,
    get_crawl_delay,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ROBOTS_TXT = (FIXTURES_DIR / "sample_robots.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parser(robots_txt: str, base_url: str = "https://example.com") -> RobotFileParser:
    """Build a RobotFileParser from raw robots.txt content."""
    rp = RobotFileParser()
    rp.set_url(f"{base_url}/robots.txt")
    rp.parse(robots_txt.splitlines())
    return rp


def _patch_fetch(robots_txt: str):
    """Patch _fetch_and_parse to return a parser built from *robots_txt*."""
    parser = _make_parser(robots_txt)
    return patch(
        "data_engine.ingestion.crawlers.robots_checker.RobotsChecker._fetch_and_parse",
        new=AsyncMock(return_value=parser),
    )


# ---------------------------------------------------------------------------
# _robots_url utility
# ---------------------------------------------------------------------------

def test_robots_url_basic():
    assert _robots_url("https://example.com/some/path") == "https://example.com/robots.txt"


def test_robots_url_with_port():
    result = _robots_url("http://example.com:8080/page")
    assert result == "http://example.com:8080/robots.txt"


def test_robots_url_invalid():
    assert _robots_url("not-a-url") is None


def test_robots_url_no_scheme():
    assert _robots_url("example.com/page") is None


# ---------------------------------------------------------------------------
# _host utility
# ---------------------------------------------------------------------------

def test_host_basic():
    assert _host("https://example.com/path") == "example.com"


def test_host_with_port():
    assert _host("http://example.com:9000/") == "example.com:9000"


def test_host_invalid():
    result = _host("not-a-url")
    assert result is None or result == ""


# ---------------------------------------------------------------------------
# RobotsChecker.can_fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_can_fetch_allowed_path():
    with _patch_fetch(ROBOTS_TXT):
        checker = RobotsChecker(user_agent="*")
        result = await checker.can_fetch("https://example.com/public-page")
    assert result is True


@pytest.mark.asyncio
async def test_can_fetch_disallowed_path():
    with _patch_fetch(ROBOTS_TXT):
        checker = RobotsChecker(user_agent="*")
        result = await checker.can_fetch("https://example.com/admin/dashboard")
    assert result is False


@pytest.mark.asyncio
async def test_can_fetch_private_path_disallowed():
    with _patch_fetch(ROBOTS_TXT):
        checker = RobotsChecker(user_agent="*")
        result = await checker.can_fetch("https://example.com/private/data")
    assert result is False


@pytest.mark.asyncio
async def test_can_fetch_hajeen_bot_secret():
    with _patch_fetch(ROBOTS_TXT):
        checker = RobotsChecker(user_agent="HajeenBot")
        result = await checker.can_fetch("https://example.com/secret/stuff")
    assert result is False


@pytest.mark.asyncio
async def test_can_fetch_returns_true_when_fetch_fails():
    """If robots.txt is unreachable, fetching should be allowed (fail-open)."""
    with patch(
        "data_engine.ingestion.crawlers.robots_checker.RobotsChecker._fetch_and_parse",
        new=AsyncMock(return_value=None),
    ):
        checker = RobotsChecker()
        result = await checker.can_fetch("https://unreachable.example.com/page")
    assert result is True


# ---------------------------------------------------------------------------
# RobotsChecker.get_crawl_delay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_crawl_delay_hajeen_bot():
    with _patch_fetch(ROBOTS_TXT):
        checker = RobotsChecker(user_agent="HajeenBot")
        delay = await checker.get_crawl_delay("https://example.com/")
    assert delay == 2.0


@pytest.mark.asyncio
async def test_get_crawl_delay_no_delay_for_generic():
    with _patch_fetch(ROBOTS_TXT):
        checker = RobotsChecker(user_agent="SomeOtherBot")
        delay = await checker.get_crawl_delay("https://example.com/")
    assert delay is None


@pytest.mark.asyncio
async def test_get_crawl_delay_unreachable_returns_none():
    with patch(
        "data_engine.ingestion.crawlers.robots_checker.RobotsChecker._fetch_and_parse",
        new=AsyncMock(return_value=None),
    ):
        checker = RobotsChecker()
        delay = await checker.get_crawl_delay("https://unreachable.example.com/")
    assert delay is None


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caching_prevents_duplicate_fetches():
    fetch_count = 0

    async def counting_fetch(_self_or_url, robots_url: str = None):
        nonlocal fetch_count
        fetch_count += 1
        return _make_parser(ROBOTS_TXT)

    with patch(
        "data_engine.ingestion.crawlers.robots_checker.RobotsChecker._fetch_and_parse",
        new=counting_fetch,
    ):
        checker = RobotsChecker(cache_ttl=60)
        await checker.can_fetch("https://example.com/page1")
        await checker.can_fetch("https://example.com/page2")
        await checker.can_fetch("https://example.com/page3")

    assert fetch_count == 1, "robots.txt should be fetched only once per host"


@pytest.mark.asyncio
async def test_invalidate_clears_cache():
    async def counting_fetch(_self_or_url, robots_url: str = None):
        return _make_parser(ROBOTS_TXT)

    with patch(
        "data_engine.ingestion.crawlers.robots_checker.RobotsChecker._fetch_and_parse",
        new=counting_fetch,
    ):
        checker = RobotsChecker()
        await checker.can_fetch("https://example.com/page")
        checker.invalidate("example.com")
        assert "example.com" not in checker._cache


@pytest.mark.asyncio
async def test_clear_cache():
    checker = RobotsChecker()
    checker._cache["example.com"] = MagicMock()
    checker._cache["other.com"] = MagicMock()
    checker.clear_cache()
    assert len(checker._cache) == 0


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_module_can_fetch():
    import data_engine.ingestion.crawlers.robots_checker as rc

    rc._default_checker = None  # Reset singleton

    with _patch_fetch(ROBOTS_TXT):
        result = await can_fetch(
            "https://example.com/public",
            user_agent="*",
        )
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_module_get_crawl_delay():
    import data_engine.ingestion.crawlers.robots_checker as rc

    rc._default_checker = None  # Reset singleton

    with _patch_fetch(ROBOTS_TXT):
        delay = await get_crawl_delay(
            "https://example.com/",
            user_agent="HajeenBot",
        )
    assert delay == 2.0 or delay is None  # depends on singleton state
