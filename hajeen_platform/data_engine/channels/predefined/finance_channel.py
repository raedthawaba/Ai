"""Finance Channel — Phase 3 (Section 3.5).

قناة المالية: تجمع محتوى مالي واقتصادي من مصادر متعددة:
- RSS feeds (Reuters Finance, Bloomberg, CNBC, MarketWatch, WSJ Markets)
- NewsAPI (finance category)
- Reddit r/investing, r/stocks, r/economics

تُعيد Article objects موحّدة جاهزة للمعالجة.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, List, Optional

from shared.schemas.article import Article
from shared.schemas.channel import ChannelConfig, ChannelStatus
from data_engine.channels.base import BaseChannel, FetchResult
from data_engine.ingestion.crawlers.rss_parser import parse_rss_feed, validate_rss_feed
from data_engine.ingestion.crawlers.robots_checker import can_fetch

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default finance RSS feeds
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.investing.com/rss/news.rss",
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://seekingalpha.com/feed.xml",
]

# Reddit subreddits للمالية
_DEFAULT_FINANCE_SUBREDDITS = [
    "investing",
    "stocks",
    "economics",
    "finance",
]


class FinanceChannel(BaseChannel):
    """قناة المحتوى المالي والاقتصادي.

    تجمع أخبار مالية من RSS feeds وReddit.

    Parameters
    ----------
    config:
        ChannelConfig يجب أن يحتوي على source_config مع:
        - rss_feeds: List[str] — قائمة RSS feeds
        - subreddits: List[str] — subreddits مالية
        - max_articles_per_feed: int — الحد الأقصى لكل feed
        - include_reddit: bool — هل يُضمّن Reddit؟
        - newsapi_key: str — مفتاح NewsAPI (اختياري)
        - newsapi_query: str — استعلام NewsAPI (افتراضي: finance)
    """

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        src = (config.source.params if config.source else {})
        self._feeds: List[str] = src.get("rss_feeds", _DEFAULT_RSS_FEEDS)
        self._subreddits: List[str] = src.get("subreddits", _DEFAULT_FINANCE_SUBREDDITS)
        self._max_per_feed: int = int(src.get("max_articles_per_feed", 20))
        self._include_reddit: bool = bool(src.get("include_reddit", True))
        self._check_robots: bool = bool(src.get("check_robots", True))
        self._newsapi_key: Optional[str] = (
            src.get("newsapi_key") or os.environ.get("NEWSAPI_KEY")
        )
        self._newsapi_query: str = src.get("newsapi_query", "finance economy stocks")
        self._reddit_limit: int = int(src.get("reddit_limit", 15))

    # ─── BaseChannel interface ───────────────────────────────────────────

    async def fetch(self, last_fetched_id: Optional[str] = None) -> FetchResult:
        """جلب المحتوى المالي من جميع المصادر.

        Parameters
        ----------
        last_fetched_id:
            معرّف آخر مقال تم جلبه.

        Returns
        -------
        FetchResult مع قائمة المقالات.
        """
        self.update_status(ChannelStatus.ACTIVE)
        all_articles: List[Article] = []
        metadata: Dict = {"channel": "finance"}

        # 1. RSS feeds (أولوية عالية)
        rss_articles, rss_stats = await self._fetch_rss_feeds()
        all_articles.extend(rss_articles)
        metadata["rss_stats"] = rss_stats
        metadata["rss_count"] = len(rss_articles)

        # 2. Reddit finance subreddits
        if self._include_reddit:
            reddit_articles, reddit_stats = await self._fetch_reddit()
            all_articles.extend(reddit_articles)
            metadata["reddit_stats"] = reddit_stats
            metadata["reddit_count"] = len(reddit_articles)

        # 3. NewsAPI (إذا كان مفتاح API متاحاً)
        if self._newsapi_key:
            news_articles, news_stats = await self._fetch_newsapi()
            all_articles.extend(news_articles)
            metadata["newsapi_stats"] = news_stats
            metadata["newsapi_count"] = len(news_articles)

        self.update_status(ChannelStatus.ACTIVE)
        logger.info(
            "FinanceChannel: fetch done total=%d rss=%d reddit=%d",
            len(all_articles),
            len(rss_articles),
            len(all_articles) - len(rss_articles),
        )

        return FetchResult(
            articles=all_articles,
            metadata=metadata,
            has_more=False,
        )

    async def validate_source(self) -> bool:
        """التحقق من صلاحية المصادر."""

        valid_count = 0
        for url in self._feeds[:2]:
            try:
                if await validate_rss_feed(url):
                    valid_count += 1
            except Exception:
                pass

        valid = valid_count > 0
        logger.info("FinanceChannel.validate_source: valid_feeds=%d", valid_count)
        return valid

    # ─── Internal fetch helpers ───────────────────────────────────────────

    async def _fetch_rss_feeds(self):
        """جلب من RSS feeds المالية."""
        articles: List[Article] = []
        stats: Dict = {}

        for feed_url in self._feeds:
            try:
                if self._check_robots:
                    allowed = await can_fetch(feed_url)
                    if not allowed:
                        stats[feed_url] = {"skipped": True, "reason": "robots_disallowed"}
                        continue

                fetched = await parse_rss_feed(
                    url=feed_url,
                    source_id=self.config.id,
                    default_language="en",
                )
                fetched = fetched[: self._max_per_feed]
                articles.extend(fetched)
                stats[feed_url] = {"fetched": len(fetched)}

            except Exception as exc:
                logger.warning("FinanceChannel: RSS error url=%s — %s", feed_url, exc)
                stats[feed_url] = {"error": str(exc)}

        return articles, stats

    async def _fetch_reddit(self):
        """جلب من Reddit finance subreddits."""
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector

        articles: List[Article] = []
        stats: Dict = {}
        connector = RedditConnector(source_id=self.config.id)
        await connector.authenticate()

        tasks = [
            connector.fetch_subreddit_posts(
                subreddit=sub,
                listing="hot",
                limit=self._reddit_limit,
            )
            for sub in self._subreddits
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sub, result in zip(self._subreddits, results):
            if isinstance(result, Exception):
                logger.warning("FinanceChannel: Reddit error r/%s — %s", sub, result)
                stats[f"r/{sub}"] = {"error": str(result)}
            else:
                articles.extend(result)
                stats[f"r/{sub}"] = {"fetched": len(result)}

        return articles, stats

    async def _fetch_newsapi(self):
        """جلب من NewsAPI."""
        from data_engine.ingestion.connectors.newsapi_connector import NewsAPIConnector

        articles: List[Article] = []
        stats: Dict = {}

        try:
            connector = NewsAPIConnector(
                api_key=self._newsapi_key,
                source_id=self.config.id,
            )
            await connector.authenticate()
            fetched = await connector.fetch(query=self._newsapi_query)
            articles.extend(fetched)
            stats["newsapi"] = {"fetched": len(fetched)}
        except Exception as exc:
            logger.warning("FinanceChannel: NewsAPI error — %s", exc)
            stats["newsapi"] = {"error": str(exc)}

        return articles, stats
