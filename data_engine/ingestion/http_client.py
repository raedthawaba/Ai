"""Async HTTP client for the data ingestion engine."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, List, Optional, Union

import httpx
from .response_models import FetchResponse, ResponseMetadata, FetchError

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]


class AsyncHTTPClient:
    """
    A robust asynchronous HTTP client for data fetching.
    Supports retries, timeouts, and user-agent rotation.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        user_agents: Optional[List[str]] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agents = user_agents or DEFAULT_USER_AGENTS
        self.default_headers = default_headers or {}
        self.client = httpx.AsyncClient(timeout=self.timeout)

    def _get_random_user_agent(self) -> str:
        return random.choice(self.user_agents)

    def _prepare_headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = self.default_headers.copy()
        headers["User-Agent"] = self._get_random_user_agent()
        if custom_headers:
            headers.update(custom_headers)
        return headers

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Union[FetchResponse, FetchError]:
        """Perform an HTTP request with retry logic."""
        full_headers = self._prepare_headers(headers)
        
        for attempt in range(self.max_retries + 1):
            start_time = time.perf_counter()
            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=full_headers,
                    **kwargs
                )
                
                elapsed = time.perf_counter() - start_time
                
                # Check for success
                if response.is_success:
                    return FetchResponse(
                        content=response.content,
                        metadata=ResponseMetadata(
                            url=str(response.url),
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            elapsed_time=elapsed,
                            content_type=response.headers.get("Content-Type"),
                            encoding=response.encoding
                        )
                    )
                
                # Handle non-success but finished requests (e.g., 404, 500)
                if attempt < self.max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
                    continue
                
                return FetchError(
                    url=url,
                    error_type="HTTPStatusError",
                    message=f"Request failed with status {response.status_code}",
                    status_code=response.status_code,
                    retry_count=attempt
                )

            except (httpx.RequestError, asyncio.TimeoutError) as exc:
                if attempt < self.max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
                    continue
                
                return FetchError(
                    url=url,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    retry_count=attempt
                )

        return FetchError(
            url=url,
            error_type="MaxRetriesExceeded",
            message=f"Exceeded max retries ({self.max_retries})",
            retry_count=self.max_retries
        )

    async def get(self, url: str, **kwargs) -> Union[FetchResponse, FetchError]:
        """Perform a GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Union[FetchResponse, FetchError]:
        """Perform a POST request."""
        return await self.request("POST", url, **kwargs)

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def __aenter__(self) -> AsyncHTTPClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
