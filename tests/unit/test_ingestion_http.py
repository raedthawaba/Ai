import pytest
import respx
import httpx
from data_engine.ingestion.http_client import AsyncHTTPClient
from data_engine.ingestion.response_models import FetchResponse, FetchError

@pytest.mark.asyncio
async def test_http_client_get_success():
    url = "https://example.com/api/data"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, content=b'{"key": "value"}', headers={"Content-Type": "application/json"}))
        
        async with AsyncHTTPClient() as client:
            response = await client.get(url)
            
            assert isinstance(response, FetchResponse)
            assert response.metadata.status_code == 200
            assert response.is_json is True
            assert response.json() == {"key": "value"}
            # The User-Agent is in the request headers, not necessarily the response headers
            # But we can verify it was sent by checking respx calls if needed, 
            # or just skip this specific assertion if response.metadata.headers only contains response headers.

@pytest.mark.asyncio
async def test_http_client_post_success():
    url = "https://example.com/api/submit"
    payload = {"name": "test"}
    async with respx.mock:
        respx.post(url).mock(return_value=httpx.Response(201, content=b"Created"))
        
        async with AsyncHTTPClient() as client:
            response = await client.post(url, json=payload)
            
            assert isinstance(response, FetchResponse)
            assert response.metadata.status_code == 201
            assert response.content == b"Created"

@pytest.mark.asyncio
async def test_http_client_retry_logic():
    url = "https://example.com/api/retry"
    async with respx.mock:
        # Mock 2 failures then 1 success
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, content=b"Success")
        ]
        
        # Use short wait for testing
        async with AsyncHTTPClient(max_retries=3) as client:
            # Monkey patch sleep to speed up test
            import asyncio
            original_sleep = asyncio.sleep
            asyncio.sleep = lambda x: original_sleep(0)
            
            try:
                response = await client.get(url)
                assert isinstance(response, FetchResponse)
                assert response.content == b"Success"
                assert route.call_count == 3
            finally:
                asyncio.sleep = original_sleep

@pytest.mark.asyncio
async def test_http_client_max_retries_exceeded():
    url = "https://example.com/api/fail"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(500))
        
        async with AsyncHTTPClient(max_retries=2) as client:
            import asyncio
            original_sleep = asyncio.sleep
            asyncio.sleep = lambda x: original_sleep(0)
            
            try:
                response = await client.get(url)
                assert isinstance(response, FetchError)
                assert response.error_type == "HTTPStatusError"
                assert response.retry_count == 2
            finally:
                asyncio.sleep = original_sleep

@pytest.mark.asyncio
async def test_http_client_timeout():
    url = "https://example.com/api/timeout"
    async with respx.mock:
        respx.get(url).side_effect = httpx.TimeoutException("Timeout")
        
        async with AsyncHTTPClient(max_retries=1) as client:
            import asyncio
            original_sleep = asyncio.sleep
            asyncio.sleep = lambda x: original_sleep(0)
            
            try:
                response = await client.get(url)
                assert isinstance(response, FetchError)
                assert response.error_type == "TimeoutException"
            finally:
                asyncio.sleep = original_sleep
