"""Tests for NewsAPIConnector — section 4.7."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
import respx

from data_engine.ingestion.connectors.newsapi_connector import (
    NewsAPIConnector,
    _parse_newsapi_date,
)
from data_engine.ingestion.connectors.base_connector import ConnectorError
from shared.schemas.article import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _newsapi_response(articles: list, total: int = None) -> httpx.Response:
    payload = {
        "status": "ok",
        "totalResults": total if total is not None else len(articles),
        "articles": articles,
    }
    return httpx.Response(200, content=json.dumps(payload).encode())


SAMPLE_RAW = [
    {
        "source": {"id": "techcrunch", "name": "TechCrunch"},
        "author": "Jane Doe",
        "title": "AI Startup Raises $100M",
        "description": "A new AI startup has raised $100M in funding.",
        "url": "https://techcrunch.com/ai-startup-100m",
        "urlToImage": "https://tc.com/img.jpg",
        "publishedAt": "2024-05-20T10:00:00Z",
        "content": "Full article content here.",
    },
    {
        "source": {"id": None, "name": "BBC"},
        "author": None,
        "title": "Global Tech News",
        "description": "Tech developments from around the world.",
        "url": "https://bbc.com/tech-news",
        "urlToImage": None,
        "publishedAt": "2024-05-19T08:00:00Z",
        "content": None,
    },
]


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authenticate_sets_header():
    c = NewsAPIConnector(api_key="testkey123")
    await c.authenticate()
    assert c._headers.get("X-Api-Key") == "testkey123"
    assert c.is_authenticated


@pytest.mark.asyncio
async def test_authenticate_reads_env_var(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", "env-key-abc")
    c = NewsAPIConnector()
    await c.authenticate()
    assert c._headers.get("X-Api-Key") == "env-key-abc"


@pytest.mark.asyncio
async def test_authenticate_raises_without_key(monkeypatch):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    c = NewsAPIConnector(api_key=None)
    with pytest.raises(ConnectorError, match="NewsAPI key"):
        await c.authenticate()


# ---------------------------------------------------------------------------
# validate_response
# ---------------------------------------------------------------------------

def test_validate_ok_response():
    c = NewsAPIConnector(api_key="k")
    assert c.validate_response({"status": "ok", "articles": []}) is True


def test_validate_error_response():
    c = NewsAPIConnector(api_key="k")
    assert c.validate_response({"status": "error", "code": "apiKeyInvalid"}) is False


def test_validate_missing_articles():
    c = NewsAPIConnector(api_key="k")
    assert c.validate_response({"status": "ok"}) is False


def test_validate_non_dict():
    c = NewsAPIConnector(api_key="k")
    assert c.validate_response([]) is False


# ---------------------------------------------------------------------------
# fetch_headlines
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_headlines_success():
    async with respx.mock:
        respx.get("https://newsapi.org/v2/top-headlines").mock(
            return_value=_newsapi_response(SAMPLE_RAW)
        )
        c = NewsAPIConnector(api_key="key")
        articles = await c.fetch_headlines(country="us")

    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)


@pytest.mark.asyncio
async def test_fetch_headlines_with_category():
    async with respx.mock:
        route = respx.get("https://newsapi.org/v2/top-headlines").mock(
            return_value=_newsapi_response(SAMPLE_RAW)
        )
        c = NewsAPIConnector(api_key="key")
        await c.fetch_headlines(category="technology", country="us")

    assert route.called
    params = dict(route.calls.last.request.url.params)
    assert params.get("category") == "technology"


@pytest.mark.asyncio
async def test_fetch_headlines_api_error_returns_empty():
    async with respx.mock:
        respx.get("https://newsapi.org/v2/top-headlines").mock(
            return_value=httpx.Response(401)
        )
        c = NewsAPIConnector(api_key="bad-key")

        import asyncio
        orig = asyncio.sleep
        asyncio.sleep = lambda x: orig(0)
        try:
            articles = await c.fetch_headlines()
        finally:
            asyncio.sleep = orig

    assert articles == []


# ---------------------------------------------------------------------------
# search_articles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_articles_success():
    async with respx.mock:
        respx.get("https://newsapi.org/v2/everything").mock(
            return_value=_newsapi_response(SAMPLE_RAW)
        )
        c = NewsAPIConnector(api_key="key")
        articles = await c.search_articles(query="python")

    assert len(articles) == 2


@pytest.mark.asyncio
async def test_search_articles_with_date_range():
    async with respx.mock:
        route = respx.get("https://newsapi.org/v2/everything").mock(
            return_value=_newsapi_response([])
        )
        c = NewsAPIConnector(api_key="key")
        from_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2024, 5, 20, tzinfo=timezone.utc)
        await c.search_articles(query="ai", from_date=from_dt, to_date=to_dt)

    params = dict(route.calls.last.request.url.params)
    assert "from" in params
    assert "to" in params


@pytest.mark.asyncio
async def test_search_articles_filters_removed():
    raw_with_removed = SAMPLE_RAW + [
        {
            "title": "[Removed]",
            "url": "https://removed.com",
            "publishedAt": "2024-05-20T10:00:00Z",
        }
    ]
    async with respx.mock:
        respx.get("https://newsapi.org/v2/everything").mock(
            return_value=_newsapi_response(raw_with_removed)
        )
        c = NewsAPIConnector(api_key="key")
        articles = await c.search_articles(query="test")

    titles = [a.title for a in articles]
    assert "[Removed]" not in titles


# ---------------------------------------------------------------------------
# fetch (main entry point)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_uses_headlines_when_no_query():
    async with respx.mock:
        route = respx.get("https://newsapi.org/v2/top-headlines").mock(
            return_value=_newsapi_response(SAMPLE_RAW, total=2)
        )
        c = NewsAPIConnector(api_key="key")
        articles = await c.fetch(max_pages=1)

    assert route.called
    assert len(articles) > 0


@pytest.mark.asyncio
async def test_fetch_uses_everything_with_query():
    async with respx.mock:
        route = respx.get("https://newsapi.org/v2/everything").mock(
            return_value=_newsapi_response(SAMPLE_RAW, total=2)
        )
        c = NewsAPIConnector(api_key="key")
        articles = await c.fetch(query="technology", max_pages=1)

    assert route.called
    assert len(articles) > 0


@pytest.mark.asyncio
async def test_fetch_deduplicates():
    duplicate_raw = SAMPLE_RAW + SAMPLE_RAW
    async with respx.mock:
        respx.get("https://newsapi.org/v2/top-headlines").mock(
            return_value=_newsapi_response(duplicate_raw, total=100)
        )
        c = NewsAPIConnector(api_key="key")
        articles = await c.fetch(max_pages=1)

    urls = [str(a.url) for a in articles]
    assert len(urls) == len(set(urls))


# ---------------------------------------------------------------------------
# Article field mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_article_has_correct_fields():
    async with respx.mock:
        respx.get("https://newsapi.org/v2/top-headlines").mock(
            return_value=_newsapi_response([SAMPLE_RAW[0]])
        )
        c = NewsAPIConnector(api_key="key", source_id="newsapi_test")
        articles = await c.fetch_headlines()

    a = articles[0]
    assert a.title == "AI Startup Raises $100M"
    assert a.metadata.source_id == "newsapi_test"
    assert a.metadata.author == "Jane Doe"
    assert str(a.url) == "https://techcrunch.com/ai-startup-100m"


# ---------------------------------------------------------------------------
# _parse_newsapi_date
# ---------------------------------------------------------------------------

def test_parse_newsapi_date_valid():
    dt = _parse_newsapi_date("2024-05-20T10:00:00Z")
    assert dt.year == 2024
    assert dt.tzinfo == timezone.utc


def test_parse_newsapi_date_none_returns_utc_now():
    dt = _parse_newsapi_date(None)
    assert dt.tzinfo == timezone.utc


def test_parse_newsapi_date_invalid_returns_utc_now():
    dt = _parse_newsapi_date("not-a-date")
    assert dt.tzinfo == timezone.utc
