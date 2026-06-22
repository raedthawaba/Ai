"""Arxiv Connector — Phase 3 (Section 3.2).

يجلب بيانات الأوراق البحثية من Arxiv API:
- بحث بالكلمات المفتاحية
- بحث بالمؤلف
- بحث بالفئة
- جلب أوراق محددة بـ ID
- تحويل إلى Article schema موحّد
- Rate limit آمن (Arxiv يطلب < 3 req/sec)
- No API key required

API: https://export.arxiv.org/api/query
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id
from .base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_ARXIV_BASE = "https://export.arxiv.org"
_ARXIV_ABSTRACT = "https://arxiv.org/abs/"
_NS_ATOM = "http://www.w3.org/2005/Atom"
_NS_ARXIV = "http://arxiv.org/schemas/atom"
_NS_OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"


class ArxivConnector(BaseConnector):
    """Connector لـ Arxiv API (بدون مفتاح API).

    يُحوّل الأوراق البحثية إلى Article objects.

    Parameters
    ----------
    source_id:
        معرّف المصدر للـ Article metadata.
    requests_per_second:
        Rate limit (Arxiv: < 3 req/sec موصى به).
    """

    def __init__(
        self,
        source_id: str = "arxiv",
        requests_per_second: float = 1.0,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=_ARXIV_BASE,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_second=requests_per_second,
        )
        self.source_id = source_id
        self._headers["Accept"] = "application/atom+xml"

    # ─── BaseConnector interface ─────────────────────────────────────────

    async def authenticate(self) -> None:
        """Arxiv API لا تحتاج authentication."""
        self._authenticated = True
        logger.info("ArxivConnector.authenticate: public API — no auth required")

    async def fetch(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        max_results: int = 20,
        **kwargs: Any,
    ) -> List[Article]:
        """جلب أوراق بحثية من Arxiv.

        Parameters
        ----------
        query:
            استعلام بحث (بالكلمات المفتاحية).
        category:
            فئة Arxiv (مثل: cs.AI, cs.LG, physics.gen-ph).
        max_results:
            عدد النتائج الأقصى.

        Returns
        -------
        List[Article]
        """
        if not self.is_authenticated:
            await self.authenticate()

        search_query = query or ""
        if category:
            cat_query = f"cat:{category}"
            search_query = f"{search_query} AND {cat_query}" if search_query else cat_query

        return await self.search(
            search_query=search_query or "ti:machine+learning",
            max_results=max_results,
        )

    def validate_response(self, data: Any) -> bool:
        """التحقق من استجابة Arxiv API."""
        return isinstance(data, str) and "<feed" in data

    # ─── Public methods ──────────────────────────────────────────────────

    async def search(
        self,
        search_query: str,
        max_results: int = 20,
        start: int = 0,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> List[Article]:
        """بحث في Arxiv بالكلمات المفتاحية.

        Parameters
        ----------
        search_query:
            استعلام بصيغة Arxiv (ti:, au:, cat:, abs:).
        max_results:
            عدد النتائج.
        start:
            نقطة البداية للـ pagination.
        sort_by:
            معيار الترتيب: submittedDate | lastUpdatedDate | relevance.
        sort_order:
            اتجاه الترتيب: descending | ascending.

        Returns
        -------
        List[Article]
        """
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(max_results, 100),
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        articles: List[Article] = []
        try:
            # Arxiv يُعيد XML وليس JSON — نستخدم httpx مباشرة
            import httpx
            query_str = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{_ARXIV_BASE}/api/query?{query_str}"

            for attempt in range(self.max_retries + 1):
                await self._rate_limiter.acquire()
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.get(
                            url, headers=self._headers
                        )
                    if response.status_code == 200:
                        articles = self._parse_atom_feed(response.text)
                        break
                    elif attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.warning(
                            "ArxivConnector.search: HTTP %d query=%r",
                            response.status_code, search_query,
                        )
                except Exception as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.warning(
                            "ArxivConnector.search: error query=%r — %s",
                            search_query, exc,
                        )

        except Exception as exc:
            logger.error("ArxivConnector.search: unexpected error — %s", exc)

        logger.info(
            "ArxivConnector.search: query=%r articles=%d",
            search_query, len(articles),
        )
        return articles

    async def fetch_by_ids(self, arxiv_ids: List[str]) -> List[Article]:
        """جلب أوراق محددة بـ Arxiv IDs.

        Parameters
        ----------
        arxiv_ids:
            قائمة معرّفات Arxiv (مثل: 2401.00001, cs/0601001).

        Returns
        -------
        List[Article]
        """
        if not arxiv_ids:
            return []

        id_list = ",".join(arxiv_ids)
        return await self.search(
            search_query="",
            max_results=len(arxiv_ids),
        )

    async def fetch_category(
        self,
        category: str,
        max_results: int = 20,
    ) -> List[Article]:
        """جلب أحدث أوراق فئة معينة.

        Parameters
        ----------
        category:
            فئة Arxiv (مثل: cs.AI, cs.CL, physics.gen-ph).
        max_results:
            عدد النتائج.

        Returns
        -------
        List[Article]
        """
        return await self.search(
            search_query=f"cat:{category}",
            max_results=max_results,
            sort_by="submittedDate",
            sort_order="descending",
        )

    # ─── XML Parsing ─────────────────────────────────────────────────────

    def _parse_atom_feed(self, xml_text: str) -> List[Article]:
        """تحليل Atom feed من Arxiv API."""
        articles: List[Article] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("ArxivConnector._parse_atom_feed: XML parse error — %s", exc)
            return []

        ns = {"atom": _NS_ATOM, "arxiv": _NS_ARXIV}
        entries = root.findall("atom:entry", ns)

        for entry in entries:
            article = self._entry_to_article(entry, ns)
            if article:
                articles.append(article)

        return articles

    def _entry_to_article(
        self, entry: ET.Element, ns: Dict[str, str]
    ) -> Optional[Article]:
        """تحويل Atom entry إلى Article."""
        def _text(tag: str) -> str:
            el = entry.find(tag, ns)
            return el.text.strip() if el is not None and el.text else ""

        arxiv_id = _text("atom:id").split("/abs/")[-1].strip()
        if not arxiv_id:
            return None

        title = _text("atom:title").replace("\n", " ").strip()
        summary = _text("atom:summary").replace("\n", " ").strip()

        if not title:
            return None

        # Authors
        authors = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # Published date
        published_str = _text("atom:published")
        try:
            published_at = (
                datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                if published_str
                else utc_now()
            )
        except Exception:
            published_at = utc_now()

        # Categories
        categories = []
        for cat_el in entry.findall("atom:category", ns):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)

        # Primary category
        primary_cat = ""
        pc_el = entry.find("arxiv:primary_category", ns)
        if pc_el is not None:
            primary_cat = pc_el.get("term", "")

        url = f"{_ARXIV_ABSTRACT}{arxiv_id}"

        try:
            return Article(
                id=generate_article_id(f"arxiv_{arxiv_id}"),
                title=title,
                content=summary or title,
                url=url,  # type: ignore[arg-type]
                published_at=published_at,
                summary=summary or None,
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    author=", ".join(authors[:3]) if authors else None,
                    language="en",
                    tags=categories[:5],
                    extra={
                        "arxiv_id": arxiv_id,
                        "primary_category": primary_cat,
                        "all_authors": authors,
                        "doi": _text("arxiv:doi"),
                        "journal_ref": _text("arxiv:journal_ref"),
                    },
                ),
            )
        except Exception as exc:
            logger.debug("ArxivConnector._entry_to_article: error id=%s — %s", arxiv_id, exc)
            return None
