"""Base Connector — section 4.6.

Abstract base class for all API connectors.  Provides:
- Authentication lifecycle (authenticate / is_authenticated)
- Generic fetch with pagination support
- Response validation
- Simple in-memory rate limiting
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from shared.schemas.article import Article

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Raised when a connector operation fails."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimiter:
    """Simple token-bucket rate limiter (in-process only).

    Parameters
    ----------
    requests_per_second:
        Maximum number of requests allowed per second.
    """

    def __init__(self, requests_per_second: float = 1.0) -> None:
        self._min_interval = 1.0 / max(requests_per_second, 0.001)
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until the next request slot is available."""
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                logger.debug("RateLimiter: waiting %.3fs", wait)
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


class BaseConnector(ABC):
    """Abstract base for all API connectors.

    Parameters
    ----------
    base_url:
        Root URL of the API (no trailing slash).
    timeout:
        Per-request timeout in seconds.
    max_retries:
        Number of retry attempts on transient failures.
    requests_per_second:
        Sustained rate limit applied before every request.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        requests_per_second: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._rate_limiter = RateLimiter(requests_per_second)
        self._authenticated = False
        self._headers: Dict[str, str] = {
            "User-Agent": "HajeenBot/1.0",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def authenticate(self) -> None:
        """Set up credentials / session headers.  Must set ``_authenticated=True``."""

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> List[Article]:
        """Fetch data from the API and return normalised Article objects."""

    @abstractmethod
    def validate_response(self, data: Any) -> bool:
        """Return ``True`` when *data* is a valid API response payload."""

    # ------------------------------------------------------------------
    # Helpers available to subclasses
    # ------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        """Return whether credentials have been applied."""
        return self._authenticated

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Execute a rate-limited, retrying GET request.

        Parameters
        ----------
        path:
            URL path (relative to ``base_url``) or absolute URL.
        params:
            Query-string parameters.
        extra_headers:
            Headers merged on top of the instance defaults.

        Returns
        -------
        Parsed JSON body.

        Raises
        ------
        ConnectorError
            On HTTP or network errors after exhausting retries.
        """
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = {**self._headers, **(extra_headers or {})}

        for attempt in range(self.max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 60))
                    logger.warning("get: rate-limited, sleeping %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code in {500, 502, 503, 504} and attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "get: server error %d, retry %d in %ds",
                        response.status_code,
                        attempt + 1,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                raise ConnectorError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )

            except httpx.RequestError as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ConnectorError(f"Network error: {exc}") from exc

        raise ConnectorError(f"Max retries ({self.max_retries}) exceeded for {url}")

    async def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        page_param: str = "page",
        page_size_param: str = "pageSize",
        page_size: int = 100,
        max_pages: int = 10,
    ) -> AsyncIterator[Any]:
        """Yield successive pages from a paginated REST endpoint.

        Parameters
        ----------
        path:
            URL path relative to ``base_url``.
        params:
            Base query-string parameters (page / page-size are added automatically).
        page_param:
            Name of the page-number query parameter.
        page_size_param:
            Name of the page-size query parameter.
        page_size:
            Records per page.
        max_pages:
            Hard ceiling to prevent runaway pagination.
        """
        base_params = dict(params or {})
        base_params[page_size_param] = page_size

        for page in range(1, max_pages + 1):
            base_params[page_param] = page
            data = await self.get(path, params=base_params)

            if not self.validate_response(data):
                logger.warning("paginate: invalid response on page %d", page)
                break

            yield data

            if not self._has_next_page(data, page, page_size):
                break

    def _has_next_page(self, data: Any, current_page: int, page_size: int) -> bool:
        """Heuristic: more pages exist when the returned item count equals page_size."""
        if isinstance(data, list):
            return len(data) >= page_size
        if isinstance(data, dict):
            items = data.get("articles") or data.get("items") or data.get("results") or []
            return len(items) >= page_size
        return False
