"""Requests Fetcher — section 4.2.

A high-level fetcher built on top of the AsyncHTTPClient that:
- Saves raw HTML/JSON responses to local storage.
- Supports batch fetching with concurrency control.
- Provides structured logging throughout.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from data_engine.ingestion.http_client import AsyncHTTPClient
from data_engine.ingestion.response_models import FetchError, FetchResponse
from data_engine.storage.raw_store.local_storage import LocalRawStorage

logger = logging.getLogger(__name__)


class RequestsFetcher:
    """High-level HTTP fetcher with raw-storage integration and logging.

    Parameters
    ----------
    storage_base_dir:
        Base directory used for raw storage.  Defaults to ``./data/raw``.
    timeout:
        Per-request timeout in seconds.
    max_retries:
        How many times to retry a failing request before giving up.
    max_concurrency:
        Maximum number of requests executed simultaneously in
        :meth:`batch_fetch`.
    """

    def __init__(
        self,
        storage_base_dir: str = "./data/raw",
        timeout: float = 30.0,
        max_retries: int = 3,
        max_concurrency: int = 10,
    ) -> None:
        self._storage = LocalRawStorage(base_dir=storage_base_dir)
        self._client = AsyncHTTPClient(timeout=timeout, max_retries=max_retries)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_html(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        save: bool = True,
    ) -> Union[FetchResponse, FetchError]:
        """Fetch a URL and return its HTML content.

        Parameters
        ----------
        url:
            Target URL.
        headers:
            Optional extra request headers.
        save:
            When ``True`` the raw response body is saved to local storage.

        Returns
        -------
        :class:`FetchResponse` on success, :class:`FetchError` on failure.
        """
        logger.info("fetch_html: starting url=%s", url)
        result = await self._client.get(url, headers=headers)

        if isinstance(result, FetchError):
            logger.warning(
                "fetch_html: failed url=%s error_type=%s message=%s retries=%d",
                url,
                result.error_type,
                result.message,
                result.retry_count,
            )
            return result

        logger.info(
            "fetch_html: success url=%s status=%d elapsed=%.3fs",
            url,
            result.metadata.status_code,
            result.metadata.elapsed_time,
        )

        if save:
            await self._save_response(result, prefix="html")

        return result

    async def fetch_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        save: bool = True,
    ) -> Union[Dict[str, Any], FetchError]:
        """Fetch a URL that returns JSON and parse the response body.

        Parameters
        ----------
        url:
            Target URL.
        params:
            Optional query-string parameters.
        headers:
            Optional extra request headers.
        save:
            When ``True`` the raw response body is saved to local storage.

        Returns
        -------
        Parsed JSON dictionary on success, :class:`FetchError` on failure.
        """
        logger.info("fetch_json: starting url=%s", url)
        result = await self._client.get(url, params=params, headers=headers)

        if isinstance(result, FetchError):
            logger.warning(
                "fetch_json: failed url=%s error_type=%s message=%s retries=%d",
                url,
                result.error_type,
                result.message,
                result.retry_count,
            )
            return result

        try:
            parsed = result.json()
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error("fetch_json: JSON parse error url=%s error=%s", url, exc)
            return FetchError(
                url=url,
                error_type="JSONDecodeError",
                message=str(exc),
                status_code=result.metadata.status_code,
                retry_count=0,
            )

        logger.info(
            "fetch_json: success url=%s status=%d elapsed=%.3fs",
            url,
            result.metadata.status_code,
            result.metadata.elapsed_time,
        )

        if save:
            await self._save_response(result, prefix="json")

        return parsed

    async def batch_fetch(
        self,
        urls: List[str],
        fetch_type: str = "html",
        headers: Optional[Dict[str, str]] = None,
        save: bool = True,
    ) -> List[Tuple[str, Union[FetchResponse, Dict[str, Any], FetchError]]]:
        """Fetch multiple URLs concurrently with a semaphore-based rate limit.

        Parameters
        ----------
        urls:
            List of URLs to fetch.
        fetch_type:
            ``"html"`` to use :meth:`fetch_html`, ``"json"`` to use
            :meth:`fetch_json`.
        headers:
            Optional extra request headers applied to every request.
        save:
            When ``True`` each raw response is saved to local storage.

        Returns
        -------
        List of ``(url, result)`` tuples preserving the original order.
        """
        logger.info("batch_fetch: starting count=%d type=%s", len(urls), fetch_type)

        async def _bounded_fetch(
            url: str,
        ) -> Tuple[str, Union[FetchResponse, Dict[str, Any], FetchError]]:
            async with self._semaphore:
                if fetch_type == "json":
                    result = await self.fetch_json(url, headers=headers, save=save)
                else:
                    result = await self.fetch_html(url, headers=headers, save=save)
                return url, result

        tasks = [_bounded_fetch(u) for u in urls]
        results = await asyncio.gather(*tasks)

        successes = sum(1 for _, r in results if not isinstance(r, FetchError))
        failures = len(results) - successes
        logger.info(
            "batch_fetch: done total=%d success=%d failed=%d",
            len(results),
            successes,
            failures,
        )

        return list(results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _save_response(self, response: FetchResponse, prefix: str) -> str:
        """Persist a fetch response body to raw storage.

        Returns the storage key (relative path).
        """
        url_slug = _url_to_slug(str(response.metadata.url))
        key = f"{prefix}/{url_slug}"

        try:
            saved_key = await self._storage.save_raw(
                data=response.content,
                key=key,
                metadata={
                    "url": str(response.metadata.url),
                    "status_code": response.metadata.status_code,
                    "content_type": response.metadata.content_type,
                    "elapsed_time": response.metadata.elapsed_time,
                },
            )
            logger.debug("_save_response: saved key=%s", saved_key)
            return saved_key
        except Exception as exc:
            logger.error("_save_response: failed key=%s error=%s", key, exc)
            return key

    async def close(self) -> None:
        """Release underlying HTTP client resources."""
        await self._client.close()

    async def __aenter__(self) -> "RequestsFetcher":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _url_to_slug(url: str, max_length: int = 80) -> str:
    """Convert a URL into a filesystem-safe slug."""
    import hashlib
    import re

    cleaned = re.sub(r"https?://", "", url)
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")

    if len(cleaned) > max_length:
        suffix = hashlib.md5(url.encode()).hexdigest()[:8]
        cleaned = cleaned[: max_length - 9] + "_" + suffix

    return cleaned or "unknown"
