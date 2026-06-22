"""YouTube Connector — Phase 3 (Section 3.2).

يجلب بيانات من YouTube Data API v3:
- قائمة فيديوهات القناة
- بحث بالكلمات المفتاحية
- تفاصيل الفيديو (عنوان، وصف، إحصائيات)
- تحويل إلى Article schema موحّد
- Rate limit handling (quota-aware)
- Pagination كاملة

المتطلبات: YOUTUBE_API_KEY في env variables.
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

_YT_BASE = "https://www.googleapis.com/youtube/v3"
_YT_WATCH = "https://www.youtube.com/watch?v="


class YouTubeConnector(BaseConnector):
    """Connector لـ YouTube Data API v3.

    يتطلب YouTube Data API key (مجاني مع quota).

    Parameters
    ----------
    api_key:
        YouTube Data API v3 key. إذا None → يقرأ YOUTUBE_API_KEY.
    source_id:
        معرّف المصدر للـ Article metadata.
    requests_per_second:
        Rate limit (YouTube quota: 10,000 units/day).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        source_id: str = "youtube",
        requests_per_second: float = 2.0,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=_YT_BASE,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_second=requests_per_second,
        )
        self._api_key: Optional[str] = api_key or os.environ.get("YOUTUBE_API_KEY")
        self.source_id = source_id

    # ─── BaseConnector interface ─────────────────────────────────────────

    async def authenticate(self) -> None:
        """YouTube API تستخدم API key — لا تحتاج OAuth."""
        if not self._api_key:
            logger.warning("YouTubeConnector: لا يوجد YOUTUBE_API_KEY")
        self._authenticated = True
        logger.info(
            "YouTubeConnector.authenticate: api_key=%s",
            "set" if self._api_key else "missing",
        )

    async def fetch(
        self,
        channel_id: Optional[str] = None,
        query: Optional[str] = None,
        max_results: int = 50,
        **kwargs: Any,
    ) -> List[Article]:
        """جلب فيديوهات من YouTube.

        Parameters
        ----------
        channel_id:
            معرّف قناة YouTube (يبدأ بـ UC...).
        query:
            بحث بالكلمات المفتاحية.
        max_results:
            عدد النتائج الأقصى.

        Returns
        -------
        List[Article]
        """
        if not self.is_authenticated:
            await self.authenticate()

        if not self._api_key:
            logger.error("YouTubeConnector.fetch: YOUTUBE_API_KEY مفقود")
            return []

        if channel_id:
            return await self.fetch_channel_videos(channel_id, max_results=max_results)
        if query:
            return await self.search_videos(query, max_results=max_results)

        logger.warning("YouTubeConnector.fetch: يجب تحديد channel_id أو query")
        return []

    def validate_response(self, data: Any) -> bool:
        """التحقق من استجابة YouTube API."""
        if not isinstance(data, dict):
            return False
        return "items" in data or "kind" in data

    # ─── Public methods ──────────────────────────────────────────────────

    async def search_videos(
        self,
        query: str,
        max_results: int = 50,
        language: str = "ar",
        order: str = "date",
        published_after: Optional[str] = None,
    ) -> List[Article]:
        """البحث عن فيديوهات بالكلمات المفتاحية.

        Parameters
        ----------
        query:
            استعلام البحث.
        max_results:
            عدد النتائج (حد أقصى 50 لكل طلب).
        language:
            رمز اللغة (ar, en, ...).
        order:
            ترتيب النتائج: date | rating | relevance | viewCount.
        published_after:
            تصفية بتاريخ النشر (RFC 3339).

        Returns
        -------
        List[Article]
        """
        params: Dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": order,
            "relevanceLanguage": language,
            "key": self._api_key,
        }
        if published_after:
            params["publishedAfter"] = published_after

        articles: List[Article] = []
        try:
            data = await self.get("/search", params=params)
            if not self.validate_response(data):
                return []

            items = data.get("items", [])
            video_ids = [
                item["id"]["videoId"]
                for item in items
                if item.get("id", {}).get("videoId")
            ]

            # جلب تفاصيل الفيديوهات
            details = await self._fetch_video_details(video_ids)
            articles = [self._video_to_article(d) for d in details if d]

        except ConnectorError as exc:
            logger.warning("YouTubeConnector.search_videos: query=%r error=%s", query, exc)

        logger.info(
            "YouTubeConnector.search_videos: query=%r articles=%d", query, len(articles)
        )
        return [a for a in articles if a is not None]

    async def fetch_channel_videos(
        self,
        channel_id: str,
        max_results: int = 50,
    ) -> List[Article]:
        """جلب أحدث فيديوهات قناة YouTube.

        Parameters
        ----------
        channel_id:
            معرّف القناة (UCxxxxxxx...).
        max_results:
            عدد الفيديوهات الأقصى.

        Returns
        -------
        List[Article]
        """
        params: Dict[str, Any] = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "date",
            "key": self._api_key,
        }

        articles: List[Article] = []
        next_page_token: Optional[str] = None
        fetched = 0

        while fetched < max_results:
            if next_page_token:
                params["pageToken"] = next_page_token
            try:
                data = await self.get("/search", params=params)
            except ConnectorError as exc:
                logger.warning(
                    "YouTubeConnector.fetch_channel_videos: channel=%s error=%s",
                    channel_id, exc,
                )
                break

            if not self.validate_response(data):
                break

            items = data.get("items", [])
            video_ids = [
                item["id"]["videoId"]
                for item in items
                if item.get("id", {}).get("videoId")
            ]

            details = await self._fetch_video_details(video_ids)
            batch = [self._video_to_article(d) for d in details if d]
            articles.extend(a for a in batch if a is not None)
            fetched += len(batch)

            next_page_token = data.get("nextPageToken")
            if not next_page_token or fetched >= max_results:
                break

        logger.info(
            "YouTubeConnector.fetch_channel_videos: channel=%s articles=%d",
            channel_id, len(articles),
        )
        return articles

    # ─── Internal helpers ─────────────────────────────────────────────────

    async def _fetch_video_details(
        self, video_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """جلب تفاصيل قائمة من الفيديوهات دفعةً واحدة."""
        if not video_ids:
            return []
        params: Dict[str, Any] = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": self._api_key,
        }
        try:
            data = await self.get("/videos", params=params)
            return data.get("items", []) if self.validate_response(data) else []
        except ConnectorError as exc:
            logger.warning("_fetch_video_details: error=%s", exc)
            return []

    def _video_to_article(self, item: Dict[str, Any]) -> Optional[Article]:
        """تحويل YouTube video item إلى Article."""
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        video_id = item.get("id", "")

        title = snippet.get("title", "").strip()
        if not title or not video_id:
            return None

        description = snippet.get("description", "").strip()
        content = description or title

        channel_title = snippet.get("channelTitle", "")
        published_str = snippet.get("publishedAt", "")
        tags = snippet.get("tags", []) or []
        category_id = snippet.get("categoryId", "")

        try:
            published_at = (
                datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                if published_str
                else utc_now()
            )
        except Exception:
            published_at = utc_now()

        url = f"{_YT_WATCH}{video_id}"

        return Article(
            id=generate_article_id(f"youtube_{video_id}"),
            title=title,
            content=content,
            url=url,  # type: ignore[arg-type]
            published_at=published_at,
            metadata=ArticleMetadata(
                source_id=self.source_id,
                author=channel_title or None,
                language=snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage") or "en",
                tags=tags[:10],
                extra={
                    "video_id": video_id,
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": channel_title,
                    "view_count": int(stats.get("viewCount", 0) or 0),
                    "like_count": int(stats.get("likeCount", 0) or 0),
                    "comment_count": int(stats.get("commentCount", 0) or 0),
                    "category_id": category_id,
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                },
            ),
        )


Optional = Optional  # re-export for type checking
