"""Tests for RequestsFetcher — section 4.2."""

from __future__ import annotations

import pytest
import respx
import httpx

from data_engine.ingestion.crawlers.requests_fetcher import RequestsFetcher, _url_to_slug
from data_engine.ingestion.response_models import FetchError, FetchResponse


# ---------------------------------------------------------------------------
# _url_to_slug utility
# ---------------------------------------------------------------------------

def test_url_to_slug_basic():
    slug = _url_to_slug("https://example.com/path/to/page")
    assert "/" not in slug
    assert len(slug) > 0


def test_url_to_slug_long_url():
    long_url = "https://example.com/" + "a" * 200
    slug = _url_to_slug(long_url, max_length=80)
    assert len(slug) <= 80


def test_url_to_slug_empty():
    slug = _url_to_slug("", max_length=80)
    assert slug == "unknown"


# ---------------------------------------------------------------------------
# fetch_html
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_html_success(tmp_path):
    url = "https://example.com/page"
    async with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body>Hello</body></html>",
                headers={"Content-Type": "text/html"},
            )
        )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        result = await fetcher.fetch_html(url, save=False)

    assert isinstance(result, FetchResponse)
    assert result.metadata.status_code == 200
    assert b"Hello" in result.content


@pytest.mark.asyncio
async def test_fetch_html_saves_to_storage(tmp_path):
    url = "https://example.com/save-test"
    async with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(200, content=b"<html>Test</html>")
        )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        result = await fetcher.fetch_html(url, save=True)

    assert isinstance(result, FetchResponse)
    # Storage should have created at least one file
    files = list(tmp_path.rglob("*"))
    assert len(files) > 0


@pytest.mark.asyncio
async def test_fetch_html_failure(tmp_path):
    url = "https://example.com/error"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(404))
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path), max_retries=1)

        import asyncio
        original_sleep = asyncio.sleep
        asyncio.sleep = lambda x: original_sleep(0)
        try:
            result = await fetcher.fetch_html(url, save=False)
        finally:
            asyncio.sleep = original_sleep

    assert isinstance(result, FetchError)


# ---------------------------------------------------------------------------
# fetch_json
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_json_success(tmp_path):
    url = "https://api.example.com/data"
    payload = {"key": "value", "number": 42}
    async with respx.mock:
        import json
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
        )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        result = await fetcher.fetch_json(url, save=False)

    assert isinstance(result, dict)
    assert result["key"] == "value"
    assert result["number"] == 42


@pytest.mark.asyncio
async def test_fetch_json_with_params(tmp_path):
    url = "https://api.example.com/search"
    async with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                content=b'{"results": []}',
                headers={"Content-Type": "application/json"},
            )
        )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        result = await fetcher.fetch_json(url, params={"q": "test"}, save=False)

    assert isinstance(result, dict)
    assert "results" in result


@pytest.mark.asyncio
async def test_fetch_json_invalid_json(tmp_path):
    url = "https://api.example.com/bad-json"
    async with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                content=b"NOT JSON AT ALL",
                headers={"Content-Type": "application/json"},
            )
        )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        result = await fetcher.fetch_json(url, save=False)

    assert isinstance(result, FetchError)
    assert result.error_type == "JSONDecodeError"


@pytest.mark.asyncio
async def test_fetch_json_network_error(tmp_path):
    url = "https://api.example.com/fail"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(503))
        fetcher = RequestsFetcher(
            storage_base_dir=str(tmp_path), max_retries=1
        )

        import asyncio
        original_sleep = asyncio.sleep
        asyncio.sleep = lambda x: original_sleep(0)
        try:
            result = await fetcher.fetch_json(url, save=False)
        finally:
            asyncio.sleep = original_sleep

    assert isinstance(result, FetchError)


# ---------------------------------------------------------------------------
# batch_fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_fetch_html(tmp_path):
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    async with respx.mock:
        for url in urls:
            respx.get(url).mock(
                return_value=httpx.Response(200, content=b"<html>ok</html>")
            )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        results = await fetcher.batch_fetch(urls, fetch_type="html", save=False)

    assert len(results) == 3
    for url, result in results:
        assert url in urls
        assert isinstance(result, FetchResponse)


@pytest.mark.asyncio
async def test_batch_fetch_preserves_order(tmp_path):
    urls = ["https://example.com/a", "https://example.com/b"]
    async with respx.mock:
        respx.get(urls[0]).mock(return_value=httpx.Response(200, content=b"A"))
        respx.get(urls[1]).mock(return_value=httpx.Response(200, content=b"B"))

        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        results = await fetcher.batch_fetch(urls, save=False)

    result_urls = [url for url, _ in results]
    assert result_urls == urls


@pytest.mark.asyncio
async def test_batch_fetch_partial_failure(tmp_path):
    urls = ["https://example.com/ok", "https://example.com/fail"]
    async with respx.mock:
        respx.get(urls[0]).mock(return_value=httpx.Response(200, content=b"ok"))
        respx.get(urls[1]).mock(return_value=httpx.Response(500))

        fetcher = RequestsFetcher(
            storage_base_dir=str(tmp_path), max_retries=1
        )

        import asyncio
        original_sleep = asyncio.sleep
        asyncio.sleep = lambda x: original_sleep(0)
        try:
            results = await fetcher.batch_fetch(urls, save=False)
        finally:
            asyncio.sleep = original_sleep

    assert len(results) == 2
    ok_results = [r for _, r in results if isinstance(r, FetchResponse)]
    err_results = [r for _, r in results if isinstance(r, FetchError)]
    assert len(ok_results) == 1
    assert len(err_results) == 1


@pytest.mark.asyncio
async def test_batch_fetch_json_type(tmp_path):
    import json

    urls = ["https://api.example.com/1", "https://api.example.com/2"]
    async with respx.mock:
        for url in urls:
            respx.get(url).mock(
                return_value=httpx.Response(
                    200,
                    content=json.dumps({"id": url}).encode(),
                    headers={"Content-Type": "application/json"},
                )
            )
        fetcher = RequestsFetcher(storage_base_dir=str(tmp_path))
        results = await fetcher.batch_fetch(urls, fetch_type="json", save=False)

    for _, result in results:
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetcher_as_context_manager(tmp_path):
    url = "https://example.com/ctx"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, content=b"ctx"))
        async with RequestsFetcher(storage_base_dir=str(tmp_path)) as fetcher:
            result = await fetcher.fetch_html(url, save=False)

    assert isinstance(result, FetchResponse)
