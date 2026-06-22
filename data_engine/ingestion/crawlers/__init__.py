"""Crawlers package — Phase 3 (Section 3.1).

يوفّر crawlers لجلب المحتوى من الويب.
"""
from .requests_fetcher import RequestsFetcher
from .rss_parser import RSSParser, parse_rss_feed, validate_rss_feed
from .robots_checker import RobotsChecker, can_fetch, get_crawl_delay
from .sitemap_parser import SitemapParser, parse_sitemap
from .playwright_crawler import (
    PlaywrightCrawler,
    PlaywrightCrawlerConfig,
    CrawlResult,
    BatchCrawlResult,
)

__all__ = [
    "RequestsFetcher",
    "RSSParser",
    "parse_rss_feed",
    "validate_rss_feed",
    "RobotsChecker",
    "can_fetch",
    "get_crawl_delay",
    "SitemapParser",
    "parse_sitemap",
    "PlaywrightCrawler",
    "PlaywrightCrawlerConfig",
    "CrawlResult",
    "BatchCrawlResult",
]
