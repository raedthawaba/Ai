"""Tests for BaseConnector and RateLimiter — section 4.6."""

from __future__ import annotations

import asyncio
import time
from typing import Any, List
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from data_engine.ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectorError,
    RateLimiter,
)
from shared.schemas.article import Article


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------

class MinimalConnector(BaseConnector):
    async def authenticate(self) -> None:
        self._authenticated = True

    async def fetch(self, **kwargs) -> List[Article]:
        return []

    def validate_response(self, data: Any) -> bool:
        return isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limiter_does_not_block_first_call():
    rl = RateLimiter(requests_per_second=10)
    start = time.monotonic()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_rate_limiter_enforces_interval():
    rl = RateLimiter(requests_per_second=10)
    await rl.acquire()
    start = time.monotonic()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.08  # ≥ 100ms - 20ms tolerance


# ---------------------------------------------------------------------------
# BaseConnector lifecycle
# ---------------------------------------------------------------------------

def test_connector_initial_state():
    c = MinimalConnector(base_url="https://api.example.com")
    assert not c.is_authenticated
    assert c.base_url == "https://api.example.com"


def test_connector_strips_trailing_slash():
    c = MinimalConnector(base_url="https://api.example.com/")
    assert c.base_url == "https://api.example.com"


@pytest.mark.asyncio
async def test_connector_authenticate_sets_flag():
    c = MinimalConnector(base_url="https://api.example.com")
    await c.authenticate()
    assert c.is_authenticated


# ---------------------------------------------------------------------------
# BaseConnector.get
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_success():
    url = "https://api.example.com/data"
    payload = {"items": [1, 2, 3]}
    async with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(200, json=payload)
        )
        c = MinimalConnector(base_url="https://api.example.com")
        result = await c.get("/data")

    assert result == payload


@pytest.mark.asyncio
async def test_get_retries_on_server_error():
    url = "https://api.example.com/flaky"
    call_count = 0

    async def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    async with respx.mock:
        respx.get(url).mock(side_effect=side_effect)

        import asyncio as aio
        orig_sleep = aio.sleep
        aio.sleep = lambda x: orig_sleep(0)
        try:
            c = MinimalConnector(
                base_url="https://api.example.com",
                requests_per_second=100,
            )
            result = await c.get("/flaky")
        finally:
            aio.sleep = orig_sleep

    assert result == {"ok": True}
    assert call_count == 3


@pytest.mark.asyncio
async def test_get_raises_on_4xx():
    url = "https://api.example.com/bad"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(404, text="Not Found"))
        c = MinimalConnector(base_url="https://api.example.com")
        with pytest.raises(ConnectorError) as exc_info:
            await c.get("/bad")
    assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_raises_on_max_retries():
    url = "https://api.example.com/always-fail"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(503))

        import asyncio as aio
        orig_sleep = aio.sleep
        aio.sleep = lambda x: orig_sleep(0)
        try:
            c = MinimalConnector(
                base_url="https://api.example.com",
                max_retries=2,
                requests_per_second=100,
            )
            with pytest.raises(ConnectorError):
                await c.get("/always-fail")
        finally:
            aio.sleep = orig_sleep


@pytest.mark.asyncio
async def test_get_with_absolute_url():
    url = "https://other.example.com/endpoint"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, json={"ok": True}))
        c = MinimalConnector(base_url="https://api.example.com")
        result = await c.get(url)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_get_with_params():
    url = "https://api.example.com/search"
    async with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(200, json=[]))
        c = MinimalConnector(base_url="https://api.example.com")
        await c.get("/search", params={"q": "test", "page": 1})
    assert route.called


# ---------------------------------------------------------------------------
# ConnectorError
# ---------------------------------------------------------------------------

def test_connector_error_stores_status_code():
    err = ConnectorError("Bad gateway", status_code=502)
    assert err.status_code == 502
    assert "Bad gateway" in str(err)


def test_connector_error_no_status_code():
    err = ConnectorError("Network error")
    assert err.status_code is None


# ---------------------------------------------------------------------------
# _has_next_page
# ---------------------------------------------------------------------------

def test_has_next_page_list_full():
    c = MinimalConnector(base_url="https://api.example.com")
    assert c._has_next_page([1] * 10, 1, 10) is True


def test_has_next_page_list_partial():
    c = MinimalConnector(base_url="https://api.example.com")
    assert c._has_next_page([1] * 5, 1, 10) is False


def test_has_next_page_dict_articles():
    c = MinimalConnector(base_url="https://api.example.com")
    assert c._has_next_page({"articles": [{}] * 100}, 1, 100) is True
    assert c._has_next_page({"articles": [{}] * 50}, 1, 100) is False
