"""Tests for CustomConnector — section 4.6."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from data_engine.ingestion.connectors.custom_connector import CustomConnector, _parse_datetime
from data_engine.ingestion.connectors.base_connector import ConnectorError
from shared.schemas.article import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_json_response(data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(data).encode(), headers={"Content-Type": "application/json"})


SAMPLE_ARTICLES = [
    {
        "title": "Python 3.12 Released",
        "url": "https://python.org/release/3.12",
        "description": "Python 3.12 is here with major improvements.",
        "publishedAt": "2024-10-01T10:00:00Z",
    },
    {
        "title": "AI Trends 2024",
        "url": "https://example.com/ai-2024",
        "description": "The biggest AI developments of 2024.",
        "publishedAt": "2024-09-15T08:00:00Z",
    },
]


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authenticate_sets_api_key_header():
    c = CustomConnector(
        base_url="https://api.example.com",
        api_key="secret-key",
        api_key_header="X-Api-Key",
        api_key_prefix="",
    )
    await c.authenticate()
    assert c._headers.get("X-Api-Key") == "secret-key"
    assert c.is_authenticated


@pytest.mark.asyncio
async def test_authenticate_with_bearer():
    c = CustomConnector(
        base_url="https://api.example.com",
        api_key="tok_abc",
        api_key_header="Authorization",
        api_key_prefix="Bearer",
    )
    await c.authenticate()
    assert c._headers["Authorization"] == "Bearer tok_abc"


@pytest.mark.asyncio
async def test_authenticate_no_key():
    c = CustomConnector(base_url="https://api.example.com")
    await c.authenticate()
    assert c.is_authenticated


# ---------------------------------------------------------------------------
# validate_response
# ---------------------------------------------------------------------------

def test_validate_response_dict():
    c = CustomConnector(base_url="https://api.example.com")
    assert c.validate_response({"articles": []}) is True


def test_validate_response_list():
    c = CustomConnector(base_url="https://api.example.com")
    assert c.validate_response([]) is True


def test_validate_response_none():
    c = CustomConnector(base_url="https://api.example.com")
    assert c.validate_response(None) is False


def test_validate_response_string():
    c = CustomConnector(base_url="https://api.example.com")
    assert c.validate_response("bad") is False


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_list_response():
    url = "https://api.example.com/articles"
    async with respx.mock:
        respx.get(url).mock(return_value=_mock_json_response(SAMPLE_ARTICLES))
        c = CustomConnector(base_url="https://api.example.com", source_id="test")
        articles = await c.fetch(endpoint="/articles")

    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)


@pytest.mark.asyncio
async def test_fetch_nested_articles_path():
    url = "https://api.example.com/data"
    payload = {"data": {"items": SAMPLE_ARTICLES}}
    async with respx.mock:
        respx.get(url).mock(return_value=_mock_json_response(payload))
        c = CustomConnector(
            base_url="https://api.example.com",
            articles_path="data.items",
        )
        articles = await c.fetch(endpoint="/data")

    assert len(articles) == 2


@pytest.mark.asyncio
async def test_fetch_with_field_map():
    url = "https://api.example.com/news"
    payload = [
        {"headline": "Breaking News", "link": "https://news.example.com/1", "body": "Details here."},
    ]
    async with respx.mock:
        respx.get(url).mock(return_value=_mock_json_response(payload))
        c = CustomConnector(
            base_url="https://api.example.com",
            field_map={"title": "headline", "url": "link", "content": "body"},
        )
        articles = await c.fetch(endpoint="/news")

    assert len(articles) == 1
    assert articles[0].title == "Breaking News"


@pytest.mark.asyncio
async def test_fetch_skips_missing_title_or_url():
    url = "https://api.example.com/bad"
    payload = [
        {"title": "No URL article"},
        {"url": "https://example.com/no-title"},
        {"title": "Valid", "url": "https://example.com/valid", "description": "ok"},
    ]
    async with respx.mock:
        respx.get(url).mock(return_value=_mock_json_response(payload))
        c = CustomConnector(base_url="https://api.example.com")
        articles = await c.fetch(endpoint="/bad")

    assert len(articles) == 1
    assert articles[0].title == "Valid"


@pytest.mark.asyncio
async def test_fetch_network_error_returns_empty():
    url = "https://api.example.com/down"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(503))

        import asyncio
        orig_sleep = asyncio.sleep
        asyncio.sleep = lambda x: orig_sleep(0)
        try:
            c = CustomConnector(
                base_url="https://api.example.com",
                max_retries=1,
            )
            articles = await c.fetch(endpoint="/down")
        finally:
            asyncio.sleep = orig_sleep

    assert articles == []


# ---------------------------------------------------------------------------
# _extract_items
# ---------------------------------------------------------------------------

def test_extract_items_from_list():
    c = CustomConnector(base_url="https://api.example.com")
    assert c._extract_items([{"a": 1}]) == [{"a": 1}]


def test_extract_items_auto_detect_articles_key():
    c = CustomConnector(base_url="https://api.example.com")
    result = c._extract_items({"articles": [{"x": 1}]})
    assert result == [{"x": 1}]


def test_extract_items_dot_path():
    c = CustomConnector(
        base_url="https://api.example.com", articles_path="data.results"
    )
    result = c._extract_items({"data": {"results": [{"id": 1}]}})
    assert result == [{"id": 1}]


def test_extract_items_invalid_path_returns_empty():
    c = CustomConnector(
        base_url="https://api.example.com", articles_path="missing.key"
    )
    assert c._extract_items({"data": {}}) == []


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------

def test_parse_datetime_iso_z():
    from datetime import timezone
    dt = _parse_datetime("2024-05-20T10:00:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2024


def test_parse_datetime_timestamp():
    from datetime import timezone
    dt = _parse_datetime(0)
    assert dt.tzinfo == timezone.utc


def test_parse_datetime_date_only():
    from datetime import timezone
    dt = _parse_datetime("2024-05-20")
    assert dt.year == 2024
