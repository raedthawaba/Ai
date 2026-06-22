"""NewsAPI Connector — section 4.7.

Connects to https://newsapi.org and provides:
- fetch_headlines()  — top headlines by country / category
- search_articles()  — full-text article search
- fetch()            — BaseConnector-compatible entry point with pagination
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id
from .base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_NEWSAPI_BASE = "https://newsapi.org/v2"
_DEFAULT_PAGE_SIZE = 100


class NewsAPIConnector(BaseConnector):
    """Connector for the NewsAPI.org REST API.

    Parameters
    ----------
    api_key:
        NewsAPI key.  If ``None``, the ``NEWSAPI_KEY`` environment variable
        is read.
    source_id:
        Identifier attached to every generated Article's metadata.
    requests_per_second:
        Sustained outgoing request rate (default 0.5 — one req per 2s).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        source_id: str = "newsapi",
        requests_per_second: float = 0.5,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=_NEWSAPI_BASE,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_second=requests_per_second,
        )
        self._api_key: str = api_key or os.environ.get("NEWSAPI_KEY", "")
        self.source_id = source_id

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        """Inject the API key as an X-Api-Key header."""
        if not self._api_key:
            raise ConnectorError("NewsAPI key is not set. Pass api_key or set NEWSAPI_KEY env var.")
        self._headers["X-Api-Key"] = self._api_key
        self._authenticated = True
        logger.info("NewsAPIConnector.authenticate: key applied")

    async def fetch(
        self,
        query: Optional[str] = None,
        from_date: Optional[datetime] = None,
        category: Optional[str] = None,
        country: str = "us",
        language: str = "en",
        max_pages: int = 3,
        **kwargs: Any,
    ) -> List[Article]:
        """Fetch articles from NewsAPI with optional pagination.

        Tries ``/top-headlines`` when no *query* is supplied, falls back to
        ``/everything`` for full-text searches.

        Parameters
        ----------
        query:
            Optional keyword query.
        from_date:
            Only return articles published after this datetime.
        category:
            Top-headlines category (business, technology, science …).
        country:
            Two-letter ISO country code for top-headlines.
        language:
            Language filter (``en``, ``ar``, …).
        max_pages:
            Maximum pages to retrieve.

        Returns
        -------
        Deduplicated list of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        articles: List[Article] = []
        seen_urls: set[str] = set()

        if query:
            articles = await self._fetch_everything(
                query=query,
                from_date=from_date,
                language=language,
                max_pages=max_pages,
                seen_urls=seen_urls,
            )
        else:
            articles = await self._fetch_top_headlines(
                category=category,
                country=country,
                language=language,
                max_pages=max_pages,
                seen_urls=seen_urls,
            )

        logger.info("NewsAPIConnector.fetch: total articles=%d", len(articles))
        return articles

    def validate_response(self, data: Any) -> bool:
        """Validate that the response contains the expected ``articles`` list."""
        return (
            isinstance(data, dict)
            and data.get("status") == "ok"
            and isinstance(data.get("articles"), list)
        )

    # ------------------------------------------------------------------
    # Public convenience methods
    # ------------------------------------------------------------------

    async def fetch_headlines(
        self,
        category: Optional[str] = None,
        country: str = "us",
        page_size: int = 20,
    ) -> List[Article]:
        """Return top headlines for *country* / *category*.

        Parameters
        ----------
        category:
            One of: business, entertainment, general, health, science,
            sports, technology.
        country:
            Two-letter ISO country code (default ``us``).
        page_size:
            Number of results per page (max 100).

        Returns
        -------
        List of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        params: Dict[str, Any] = {
            "country": country,
            "pageSize": min(page_size, 100),
        }
        if category:
            params["category"] = category

        try:
            data = await self.get("/top-headlines", params=params)
        except ConnectorError as exc:
            logger.error("fetch_headlines: %s", exc)
            return []

        if not self.validate_response(data):
            return []

        return self._parse_articles(data["articles"], language=None)

    async def search_articles(
        self,
        query: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        language: str = "en",
        sort_by: str = "publishedAt",
        page_size: int = 20,
        page: int = 1,
    ) -> List[Article]:
        """Search articles by keyword using the ``/everything`` endpoint.

        Parameters
        ----------
        query:
            Free-text search query.
        from_date:
            Start of date range (inclusive).
        to_date:
            End of date range (inclusive).
        language:
            Two-letter language code.
        sort_by:
            One of ``relevancy``, ``popularity``, ``publishedAt``.
        page_size:
            Results per page (max 100).
        page:
            Page number starting from 1.

        Returns
        -------
        List of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        params: Dict[str, Any] = {
            "q": query,
            "language": language,
            "sortBy": sort_by,
            "pageSize": min(page_size, 100),
            "page": page,
        }
        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%dT%H:%M:%S")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%dT%H:%M:%S")

        try:
            data = await self.get("/everything", params=params)
        except ConnectorError as exc:
            logger.error("search_articles: %s", exc)
            return []

        if not self.validate_response(data):
            return []

        return self._parse_articles(data["articles"], language=language)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_top_headlines(
        self,
        category: Optional[str],
        country: str,
        language: str,
        max_pages: int,
        seen_urls: set[str],
    ) -> List[Article]:
        articles: List[Article] = []
        params: Dict[str, Any] = {
            "country": country,
            "pageSize": _DEFAULT_PAGE_SIZE,
        }
        if category:
            params["category"] = category

        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                data = await self.get("/top-headlines", params=params)
            except ConnectorError as exc:
                logger.warning("_fetch_top_headlines: page=%d error=%s", page, exc)
                break

            if not self.validate_response(data):
                break

            batch = self._parse_articles(data["articles"], language=language)
            new = []
            for a in batch:
                url = str(a.url)
                if url not in seen_urls:
                    seen_urls.add(url)
                    new.append(a)
            articles.extend(new)

            total = data.get("totalResults", 0)
            if len(articles) >= total or len(batch) < _DEFAULT_PAGE_SIZE:
                break

        return articles

    async def _fetch_everything(
        self,
        query: str,
        from_date: Optional[datetime],
        language: str,
        max_pages: int,
        seen_urls: set[str],
    ) -> List[Article]:
        articles: List[Article] = []
        params: Dict[str, Any] = {
            "q": query,
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": _DEFAULT_PAGE_SIZE,
        }
        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%dT%H:%M:%S")

        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                data = await self.get("/everything", params=params)
            except ConnectorError as exc:
                logger.warning("_fetch_everything: page=%d error=%s", page, exc)
                break

            if not self.validate_response(data):
                break

            batch = self._parse_articles(data["articles"], language=language)
            new = []
            for a in batch:
                url = str(a.url)
                if url not in seen_urls:
                    seen_urls.add(url)
                    new.append(a)
            articles.extend(new)

            total = data.get("totalResults", 0)
            if len(articles) >= total or len(batch) < _DEFAULT_PAGE_SIZE:
                break

        return articles

    def _parse_articles(
        self,
        raw_articles: List[Dict[str, Any]],
        language: Optional[str],
    ) -> List[Article]:
        """Convert NewsAPI article dicts to :class:`Article` objects."""
        articles: List[Article] = []
        for raw in raw_articles:
            article = self._raw_to_article(raw, language=language)
            if article:
                articles.append(article)
        return articles

    def _raw_to_article(
        self, raw: Dict[str, Any], language: Optional[str]
    ) -> Optional[Article]:
        """Map a single NewsAPI article dict to an :class:`Article`."""
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()

        if not title or not url or title == "[Removed]":
            return None

        content = (
            raw.get("content")
            or raw.get("description")
            or title
        ).strip()

        published_at = _parse_newsapi_date(raw.get("publishedAt"))
        source_name = raw.get("source", {}).get("name", self.source_id)
        author = raw.get("author")

        try:
            return Article(
                id=generate_article_id(url),
                title=title,
                content=content,
                url=url,  # type: ignore[arg-type]
                published_at=published_at,
                summary=raw.get("description"),
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    author=author or None,
                    language=language or "en",
                    extra={
                        "source_name": source_name,
                        "url_to_image": raw.get("urlToImage"),
                    },
                ),
            )
        except Exception as exc:
            logger.debug("_raw_to_article: skip url=%s error=%s", url, exc)
            return None


def _parse_newsapi_date(raw: Optional[str]) -> datetime:
    """Parse NewsAPI's ISO 8601 date string to a UTC datetime."""
    if not raw:
        return utc_now()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return utc_now()
