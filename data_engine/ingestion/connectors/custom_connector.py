"""Custom (generic REST) Connector — section 4.6.

A concrete, configurable connector that can talk to any JSON REST API
without requiring a dedicated subclass.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id
from .base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class CustomConnector(BaseConnector):
    """Generic REST API connector configurable at runtime.

    Parameters
    ----------
    base_url:
        Root URL of the target API.
    api_key:
        Optional bearer token or API key.
    api_key_header:
        HTTP header name used to send the key (default: ``Authorization``).
    api_key_prefix:
        Token prefix such as ``Bearer`` or ``Token`` (default: ``Bearer``).
    source_id:
        Identifier attached to every Article's metadata.
    articles_path:
        Dot-separated path to the articles list within the JSON response,
        e.g. ``"data.items"``.  If empty the root list/dict is used.
    field_map:
        Mapping from Article field names to the API's field names, e.g.
        ``{"title": "headline", "url": "link"}``.
    requests_per_second:
        Rate limit for outgoing requests.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        api_key_header: str = "Authorization",
        api_key_prefix: str = "Bearer",
        source_id: str = "custom",
        articles_path: str = "",
        field_map: Optional[Dict[str, str]] = None,
        requests_per_second: float = 2.0,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_second=requests_per_second,
        )
        self._api_key = api_key
        self._api_key_header = api_key_header
        self._api_key_prefix = api_key_prefix
        self.source_id = source_id
        self._articles_path = articles_path
        self._field_map = field_map or {}

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        """Inject API key into default headers if provided."""
        if self._api_key:
            self._headers[self._api_key_header] = (
                f"{self._api_key_prefix} {self._api_key}".strip()
            )
        self._authenticated = True
        logger.info("CustomConnector.authenticate: headers updated source=%s", self.source_id)

    async def fetch(
        self,
        endpoint: str = "/",
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Article]:
        """Fetch articles from *endpoint* and normalise them.

        Parameters
        ----------
        endpoint:
            API path relative to ``base_url`` (or absolute URL).
        params:
            Query-string parameters forwarded to the API.

        Returns
        -------
        List of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        try:
            data = await self.get(endpoint, params=params)
        except ConnectorError as exc:
            logger.error("CustomConnector.fetch: error endpoint=%s %s", endpoint, exc)
            return []

        if not self.validate_response(data):
            logger.warning("CustomConnector.fetch: invalid response endpoint=%s", endpoint)
            return []

        raw_items = self._extract_items(data)
        articles = [self._to_article(item) for item in raw_items if item]
        articles = [a for a in articles if a is not None]

        logger.info(
            "CustomConnector.fetch: endpoint=%s items=%d articles=%d",
            endpoint,
            len(raw_items),
            len(articles),
        )
        return articles

    def validate_response(self, data: Any) -> bool:
        """Accept any non-None JSON payload (dict or list)."""
        return data is not None and isinstance(data, (dict, list))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        """Navigate dot-separated path to the items list in the response."""
        if not self._articles_path:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("articles", "items", "results", "data", "entries"):
                    if isinstance(data.get(key), list):
                        return data[key]
            return [data] if isinstance(data, dict) else []

        current: Any = data
        for part in self._articles_path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return []
            if current is None:
                return []

        return current if isinstance(current, list) else [current]

    def _map_field(self, item: Dict[str, Any], article_field: str) -> Any:
        """Look up *article_field* in *item* using the configured field map."""
        api_field = self._field_map.get(article_field, article_field)
        return item.get(api_field) or item.get(article_field)

    def _to_article(self, item: Dict[str, Any]) -> Optional[Article]:
        """Convert a raw API item dict to an :class:`Article`."""
        title = self._map_field(item, "title")
        url = self._map_field(item, "url") or self._map_field(item, "link")
        content = (
            self._map_field(item, "content")
            or self._map_field(item, "description")
            or self._map_field(item, "body")
            or title
        )

        if not title or not url:
            return None

        published_raw = self._map_field(item, "published_at") or self._map_field(item, "publishedAt")
        published_at = _parse_datetime(published_raw) if published_raw else utc_now()

        try:
            return Article(
                id=generate_article_id(str(url)),
                title=str(title).strip(),
                content=str(content).strip(),
                url=str(url),  # type: ignore[arg-type]
                published_at=published_at,
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    language="en",
                    extra={"raw": item},
                ),
            )
        except Exception as exc:
            logger.debug("CustomConnector._to_article: skip url=%s error=%s", url, exc)
            return None


def _parse_datetime(value: Any):
    """Best-effort datetime parser for arbitrary string/timestamp values."""
    from datetime import datetime, timezone

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    return utc_now()
