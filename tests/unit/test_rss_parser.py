"""Tests for RSSParser — section 4.3."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock

import feedparser
import pytest

from data_engine.ingestion.crawlers.rss_parser import (
    RSSParser,
    parse_rss_feed,
    validate_rss_feed,
    _entry_to_article,
    _parse_published,
    _detect_feed_language,
    _generate_article_id,
)
from shared.schemas.article import Article

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_RSS = (FIXTURES_DIR / "sample_rss.xml").read_text(encoding="utf-8")
SAMPLE_RSS_EN = (FIXTURES_DIR / "sample_rss_en.xml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_feedparser(xml_content: str):
    """Return a patcher that makes feedparser.parse return a parsed feed from XML."""
    feed = feedparser.parse(xml_content)

    def fake_parse(url, *args, **kwargs):
        return feed

    return patch("feedparser.parse", side_effect=fake_parse)


# ---------------------------------------------------------------------------
# parse_rss_feed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_rss_arabic_feed():
    with _mock_feedparser(SAMPLE_RSS):
        articles = await parse_rss_feed(
            "https://techexample.com/feed",
            source_id="test_channel",
        )

    assert len(articles) == 2
    for article in articles:
        assert isinstance(article, Article)
        assert article.title
        assert article.content
        assert str(article.url)


@pytest.mark.asyncio
async def test_parse_rss_english_feed():
    with _mock_feedparser(SAMPLE_RSS_EN):
        articles = await parse_rss_feed(
            "https://technews.example.com/feed",
            source_id="test_en",
            default_language="en",
        )

    assert len(articles) == 2
    for article in articles:
        assert article.metadata.language == "en"


@pytest.mark.asyncio
async def test_parse_rss_article_fields():
    with _mock_feedparser(SAMPLE_RSS):
        articles = await parse_rss_feed("https://techexample.com/feed", source_id="src1")

    first = articles[0]
    assert first.title
    assert first.metadata.source_id == "src1"
    assert str(first.url).startswith("https://")
    assert first.published_at is not None


@pytest.mark.asyncio
async def test_parse_rss_categories():
    with _mock_feedparser(SAMPLE_RSS):
        articles = await parse_rss_feed("https://techexample.com/feed", source_id="s")

    # First article should have categories
    assert isinstance(articles[0].metadata.tags, list)


@pytest.mark.asyncio
async def test_parse_rss_empty_feed():
    empty_xml = '<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>'
    with _mock_feedparser(empty_xml):
        articles = await parse_rss_feed("https://example.com/empty")

    assert articles == []


@pytest.mark.asyncio
async def test_parse_rss_network_error():
    def raise_error(*args, **kwargs):
        raise ConnectionError("Network failure")

    with patch("feedparser.parse", side_effect=raise_error):
        articles = await parse_rss_feed("https://down.example.com/feed")

    assert articles == []


@pytest.mark.asyncio
async def test_parse_rss_unique_ids():
    with _mock_feedparser(SAMPLE_RSS):
        articles = await parse_rss_feed("https://techexample.com/feed", source_id="s")

    ids = [a.id for a in articles]
    assert len(ids) == len(set(ids)), "Article IDs should be unique"


# ---------------------------------------------------------------------------
# validate_rss_feed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_valid_feed():
    with _mock_feedparser(SAMPLE_RSS):
        result = await validate_rss_feed("https://techexample.com/feed")
    assert result is True


@pytest.mark.asyncio
async def test_validate_empty_channel_with_title():
    xml = '<?xml version="1.0"?><rss version="2.0"><channel><title>Valid Feed</title></channel></rss>'
    with _mock_feedparser(xml):
        result = await validate_rss_feed("https://example.com/valid")
    assert result is True


@pytest.mark.asyncio
async def test_validate_bozo_feed():
    def make_bozo(*args, **kwargs):
        feed = feedparser.FeedParserDict(bozo=True)
        feed["entries"] = []
        feed["feed"] = feedparser.FeedParserDict()
        return feed

    with patch("feedparser.parse", side_effect=make_bozo):
        result = await validate_rss_feed("https://broken.example.com/feed")
    assert result is False


@pytest.mark.asyncio
async def test_validate_network_error():
    with patch("feedparser.parse", side_effect=Exception("timeout")):
        result = await validate_rss_feed("https://unreachable.example.com/feed")
    assert result is False


# ---------------------------------------------------------------------------
# RSSParser class
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rss_parser_class_parse():
    parser = RSSParser(source_id="news", default_language="ar")
    with _mock_feedparser(SAMPLE_RSS):
        articles = await parser.parse("https://techexample.com/feed")
    assert len(articles) > 0


@pytest.mark.asyncio
async def test_rss_parser_class_validate_valid():
    parser = RSSParser()
    with _mock_feedparser(SAMPLE_RSS):
        result = await parser.validate("https://techexample.com/feed")
    assert result is True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def test_generate_article_id_is_deterministic():
    url = "https://example.com/article/123"
    assert _generate_article_id(url) == _generate_article_id(url)


def test_generate_article_id_different_urls():
    id1 = _generate_article_id("https://a.com/1")
    id2 = _generate_article_id("https://a.com/2")
    assert id1 != id2


def test_generate_article_id_has_prefix():
    article_id = _generate_article_id("https://example.com/x")
    assert article_id.startswith("art_")
