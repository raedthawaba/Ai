"""Science Channel — Phase 3 (Section 3.5).

قناة العلوم: تجمع محتوى علمي من مصادر متعددة:
- ArXiv (physics, biology, chemistry, math, cs)
- RSS feeds (Nature, Science, ScienceDaily, PubMed)
- NASA news, ESA news
- Scientific American

تُعيد Article objects موحّدة جاهزة للمعالجة.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from shared.schemas.article import Article
from shared.schemas.channel import ChannelConfig, ChannelStatus
from data_engine.channels.base import BaseChannel, FetchResult
from data_engine.ingestion.crawlers.rss_parser import parse_rss_feed, validate_rss_feed
from data_engine.ingestion.crawlers.robots_checker import can_fetch

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default science RSS feeds
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_RSS_FEEDS = [
    "https://www.nature.com/nature.rss",
    "https://www.sciencedaily.com/rss/all.xml",
    "https://feeds.newscientist.com/full-rss-feed",
    "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "https://www.quantamagazine.org/feed/",
    "https://phys.org/rss-feed/",
]

# ArXiv categories للعلوم
_DEFAULT_ARXIV_CATEGORIES = [
    "physics.gen-ph",
    "q-bio.GN",
    "cond-mat.str-el",
    "astro-ph.GA",
    "cs.AI",
]


class ScienceChannel(BaseChannel):
    """قناة المحتوى العلمي.

    تجمع أوراقاً بحثية ومقالات علمية من ArXiv وRSS feeds.

    Parameters
    ----------
    config:
        ChannelConfig يجب أن يحتوي على source_config مع:
        - rss_feeds: List[str] — قائمة RSS feeds
        - arxiv_categories: List[str] — فئات ArXiv
        - arxiv_max_per_category: int — الحد الأقصى لكل فئة
        - max_articles_per_feed: int — الحد الأقصى لكل feed
        - include_arxiv: bool — هل يُضمّن ArXiv؟
    """

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        src = (config.source.params if config.source else {})
        self._feeds: List[str] = src.get("rss_feeds", _DEFAULT_RSS_FEEDS)
        self._arxiv_categories: List[str] = src.get(
            "arxiv_categories", _DEFAULT_ARXIV_CATEGORIES
        )
        self._arxiv_max: int = int(src.get("arxiv_max_per_category", 10))
        self._max_per_feed: int = int(src.get("max_articles_per_feed", 15))
        self._include_arxiv: bool = bool(src.get("include_arxiv", True))
        self._check_robots: bool = bool(src.get("check_robots", True))

    # ─── BaseChannel interface ───────────────────────────────────────────

    async def fetch(self, last_fetched_id: Optional[str] = None) -> FetchResult:
        """جلب المحتوى العلمي من جميع المصادر.

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
        metadata: Dict = {"channel": "science"}

        # 1. RSS feeds
        rss_articles, rss_stats = await self._fetch_rss_feeds()
        all_articles.extend(rss_articles)
        metadata["rss_stats"] = rss_stats
        metadata["rss_count"] = len(rss_articles)

        # 2. ArXiv papers
        if self._include_arxiv:
            arxiv_articles, arxiv_stats = await self._fetch_arxiv()
            all_articles.extend(arxiv_articles)
            metadata["arxiv_stats"] = arxiv_stats
            metadata["arxiv_count"] = len(arxiv_articles)

        self.update_status(ChannelStatus.ACTIVE)
        logger.info(
            "ScienceChannel: fetch done total=%d rss=%d arxiv=%d",
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

        valid_rss = 0
        for url in self._feeds[:2]:
            try:
                if await validate_rss_feed(url):
                    valid_rss += 1
            except Exception:
                pass

        valid = valid_rss > 0
        logger.info("ScienceChannel.validate_source: valid_rss=%d", valid_rss)
        return valid

    # ─── Internal fetch helpers ───────────────────────────────────────────

    async def _fetch_rss_feeds(self):
        """جلب من جميع RSS feeds."""
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
                logger.warning("ScienceChannel: RSS error url=%s — %s", feed_url, exc)
                stats[feed_url] = {"error": str(exc)}

        return articles, stats

    async def _fetch_arxiv(self):
        """جلب من ArXiv."""
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector

        articles: List[Article] = []
        stats: Dict = {}
        connector = ArxivConnector(source_id=self.config.id)
        await connector.authenticate()

        tasks = [
            connector.fetch_category(cat, max_results=self._arxiv_max)
            for cat in self._arxiv_categories
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for cat, result in zip(self._arxiv_categories, results):
            if isinstance(result, Exception):
                logger.warning("ScienceChannel: ArXiv error cat=%s — %s", cat, result)
                stats[cat] = {"error": str(result)}
            else:
                articles.extend(result)
                stats[cat] = {"fetched": len(result)}

        return articles, stats
