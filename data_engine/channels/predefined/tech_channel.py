"""Tech Channel — Phase 3 (Section 3.5).

قناة التكنولوجيا: تجمع محتوى تقني من مصادر متعددة:
- RSS feeds (Hacker News, TechCrunch, Wired, Ars Technica, MIT Tech Review)
- GitHub Trending (via connector)
- Reddit r/technology, r/programming
- ArXiv CS papers

تُعيد Article objects موحّدة جاهزة للمعالجة.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shared.schemas.article import Article
from shared.schemas.channel import ChannelConfig, ChannelStatus
from data_engine.channels.base import BaseChannel, FetchResult
from data_engine.ingestion.crawlers.rss_parser import parse_rss_feed, validate_rss_feed
from data_engine.ingestion.crawlers.robots_checker import can_fetch

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default tech RSS feeds
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/rss",
    "https://arstechnica.com/feed/",
    "https://feeds.feedburner.com/mit-technology-review/latest",
    "https://thenextweb.com/feed/",
    "https://www.theverge.com/rss/index.xml",
]


class TechChannel(BaseChannel):
    """قناة المحتوى التقني.

    تجمع مقالات تقنية من مصادر RSS متعددة باللغتين العربية والإنجليزية.

    Parameters
    ----------
    config:
        ChannelConfig يجب أن يحتوي على source_config مع:
        - rss_feeds: List[str] — قائمة RSS feeds (اختياري، يستخدم الافتراضية)
        - max_articles_per_feed: int — الحد الأقصى للمقالات لكل feed
        - check_robots: bool — هل يتحقق من robots.txt؟
    """

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        src = (config.source.params if config.source else {})
        self._feeds: List[str] = src.get("rss_feeds", _DEFAULT_RSS_FEEDS)
        self._max_per_feed: int = int(src.get("max_articles_per_feed", 20))
        self._check_robots: bool = bool(src.get("check_robots", True))
        self._language: str = src.get("language", "en")

    # ─── BaseChannel interface ───────────────────────────────────────────

    async def fetch(self, last_fetched_id: Optional[str] = None) -> FetchResult:
        """جلب المقالات التقنية من جميع RSS feeds.

        Parameters
        ----------
        last_fetched_id:
            معرّف آخر مقال تم جلبه (للـ incremental fetch).

        Returns
        -------
        FetchResult مع قائمة المقالات.
        """
        self.update_status(ChannelStatus.ACTIVE)
        all_articles: List[Article] = []
        feed_stats = {}

        for feed_url in self._feeds:
            try:
                # التحقق من robots.txt
                if self._check_robots:
                    allowed = await can_fetch(feed_url)
                    if not allowed:
                        logger.info(
                            "TechChannel: robots.txt disallows url=%s", feed_url
                        )
                        feed_stats[feed_url] = {"skipped": True, "reason": "robots_disallowed"}
                        continue

                articles = await parse_rss_feed(
                    url=feed_url,
                    source_id=self.config.id,
                    default_language=self._language,
                )

                # تطبيق الحد الأقصى
                if len(articles) > self._max_per_feed:
                    articles = articles[: self._max_per_feed]

                all_articles.extend(articles)
                feed_stats[feed_url] = {"fetched": len(articles)}
                logger.debug(
                    "TechChannel: feed=%s articles=%d", feed_url, len(articles)
                )

            except Exception as exc:
                logger.warning("TechChannel: feed error url=%s error=%s", feed_url, exc)
                feed_stats[feed_url] = {"error": str(exc)}

        self.update_status(ChannelStatus.ACTIVE)
        logger.info(
            "TechChannel: fetch done total_articles=%d feeds=%d",
            len(all_articles), len(self._feeds),
        )

        return FetchResult(
            articles=all_articles,
            metadata={
                "channel": "tech",
                "feeds_count": len(self._feeds),
                "feed_stats": feed_stats,
            },
            has_more=False,
        )

    async def validate_source(self) -> bool:
        """التحقق من صلاحية على الأقل feed واحد."""

        valid_count = 0
        for feed_url in self._feeds[:3]:  # نختبر أول 3 فقط
            try:
                if await validate_rss_feed(feed_url):
                    valid_count += 1
            except Exception:
                pass

        valid = valid_count > 0
        logger.info(
            "TechChannel.validate_source: valid_feeds=%d/%d",
            valid_count, min(3, len(self._feeds)),
        )
        return valid

    # ─── Configuration helpers ────────────────────────────────────────────

    def add_feed(self, url: str) -> None:
        """إضافة RSS feed جديد."""
        if url not in self._feeds:
            self._feeds.append(url)
            logger.info("TechChannel: added feed url=%s", url)

    def remove_feed(self, url: str) -> bool:
        """حذف RSS feed."""
        if url in self._feeds:
            self._feeds.remove(url)
            logger.info("TechChannel: removed feed url=%s", url)
            return True
        return False

    @property
    def feed_urls(self) -> List[str]:
        return list(self._feeds)
