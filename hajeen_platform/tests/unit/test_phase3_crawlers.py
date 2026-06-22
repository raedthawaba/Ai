"""اختبارات Phase 3 — Section 3.1: Crawlers.

يغطّي:
- PlaywrightCrawler (fallback mode)
- CrawlResult properties
- BatchCrawlResult
- URL validation
- content-type detection
- Arabic content detection
- RequestsFetcher batch_fetch
- RobotsChecker
"""
from __future__ import annotations

import asyncio
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightCrawler
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlResult:
    def test_word_count_empty(self):
        from data_engine.ingestion.crawlers.playwright_crawler import CrawlResult
        r = CrawlResult(url="http://example.com", success=True, text="")
        assert r.word_count == 0

    def test_word_count(self):
        from data_engine.ingestion.crawlers.playwright_crawler import CrawlResult
        r = CrawlResult(url="http://x.com", success=True, text="hello world foo bar")
        assert r.word_count == 4

    def test_has_content_false_when_short(self):
        from data_engine.ingestion.crawlers.playwright_crawler import CrawlResult
        r = CrawlResult(url="http://x.com", success=True, text="hi")
        assert not r.has_content

    def test_has_content_true_when_long(self):
        from data_engine.ingestion.crawlers.playwright_crawler import CrawlResult
        r = CrawlResult(url="http://x.com", success=True, text="x " * 100)
        assert r.has_content


class TestBatchCrawlResult:
    def test_success_rate_zero_when_no_results(self):
        from data_engine.ingestion.crawlers.playwright_crawler import BatchCrawlResult
        b = BatchCrawlResult(total=0)
        assert b.success_rate == 0.0

    def test_success_rate(self):
        from data_engine.ingestion.crawlers.playwright_crawler import BatchCrawlResult
        b = BatchCrawlResult(total=4, success=3, failed=1)
        assert b.success_rate == pytest.approx(0.75)


class TestPlaywrightCrawlerURLValidation:
    def test_valid_http(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        assert PlaywrightCrawler.validate_url("http://example.com") is True

    def test_valid_https(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        assert PlaywrightCrawler.validate_url("https://example.com/path?q=1") is True

    def test_invalid_ftp(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        assert PlaywrightCrawler.validate_url("ftp://example.com") is False

    def test_invalid_empty(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        assert PlaywrightCrawler.validate_url("") is False

    def test_invalid_no_host(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        assert PlaywrightCrawler.validate_url("http://") is False


class TestContentTypeDetection:
    def _make_result(self, content_type="", html=""):
        from data_engine.ingestion.crawlers.playwright_crawler import CrawlResult
        return CrawlResult(url="http://x.com", success=True,
                          content_type=content_type, html=html)

    def test_json_content_type(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        crawler = PlaywrightCrawler()
        result = self._make_result("application/json")
        assert crawler.detect_content_type(result) == "json"

    def test_xml_content_type(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        crawler = PlaywrightCrawler()
        result = self._make_result("application/xml")
        assert crawler.detect_content_type(result) == "xml"

    def test_html_from_content_type(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        crawler = PlaywrightCrawler()
        result = self._make_result("text/html")
        assert crawler.detect_content_type(result) == "html"

    def test_html_from_tag(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        crawler = PlaywrightCrawler()
        result = self._make_result("", "<!DOCTYPE html>")
        assert crawler.detect_content_type(result) == "html"

    def test_unknown(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        crawler = PlaywrightCrawler()
        result = self._make_result("", "binary garbage")
        assert crawler.detect_content_type(result) == "unknown"


class TestArabicDetection:
    def test_arabic_text(self):
        from data_engine.ingestion.crawlers.playwright_crawler import (
            PlaywrightCrawler, CrawlResult
        )
        crawler = PlaywrightCrawler()
        r = CrawlResult(url="http://x.com", success=True,
                       text="مرحبا بالعالم هذا نص عربي طويل نسبياً")
        assert crawler.is_arabic_content(r) is True

    def test_english_text(self):
        from data_engine.ingestion.crawlers.playwright_crawler import (
            PlaywrightCrawler, CrawlResult
        )
        crawler = PlaywrightCrawler()
        r = CrawlResult(url="http://x.com", success=True,
                       text="hello world this is english text only")
        assert crawler.is_arabic_content(r) is False

    def test_empty_text(self):
        from data_engine.ingestion.crawlers.playwright_crawler import (
            PlaywrightCrawler, CrawlResult
        )
        crawler = PlaywrightCrawler()
        r = CrawlResult(url="http://x.com", success=True, text="")
        assert crawler.is_arabic_content(r) is False


class TestPlaywrightCrawlerFallback:
    """اختبار crawler في fallback mode (بدون Playwright حقيقي)."""

    @pytest.mark.asyncio
    async def test_crawl_invalid_url_returns_failure(self):
        """URL خاطئ يجب أن يُعيد CrawlResult.success=False."""
        from data_engine.ingestion.crawlers.playwright_crawler import (
            PlaywrightCrawler, PlaywrightCrawlerConfig
        )
        config = PlaywrightCrawlerConfig(max_retries=0, timeout_ms=3000)
        crawler = PlaywrightCrawler(config=config)
        result = await crawler.crawl("http://localhost:19999/nonexistent_url_test")
        assert not result.success
        assert result.url == "http://localhost:19999/nonexistent_url_test"

    @pytest.mark.asyncio
    async def test_batch_crawl_returns_correct_count(self):
        """batch_crawl يُعيد نفس عدد URLs المُدخلة."""
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawler
        crawler = PlaywrightCrawler()
        urls = [
            "http://localhost:19999/a",
            "http://localhost:19999/b",
            "http://localhost:19999/c",
        ]
        result = await crawler.crawl_batch(urls)
        assert result.total == 3
        assert len(result.results) == 3


# ─────────────────────────────────────────────────────────────────────────────
# RobotsChecker
# ─────────────────────────────────────────────────────────────────────────────

class TestRobotsChecker:
    def test_init_defaults(self):
        from data_engine.ingestion.crawlers.robots_checker import RobotsChecker
        checker = RobotsChecker()
        assert checker.user_agent == "HajeenBot/1.0"
        assert checker.cache_ttl == 3600.0

    def test_custom_params(self):
        from data_engine.ingestion.crawlers.robots_checker import RobotsChecker
        checker = RobotsChecker(user_agent="TestBot/2.0", cache_ttl=600.0)
        assert checker.user_agent == "TestBot/2.0"
        assert checker.cache_ttl == 600.0

    def test_clear_cache(self):
        from data_engine.ingestion.crawlers.robots_checker import RobotsChecker
        checker = RobotsChecker()
        checker._cache["example.com"] = object()  # type: ignore
        checker.clear_cache()
        assert len(checker._cache) == 0

    def test_invalidate_specific_host(self):
        from data_engine.ingestion.crawlers.robots_checker import RobotsChecker
        checker = RobotsChecker()
        checker._cache["foo.com"] = object()  # type: ignore
        checker._cache["bar.com"] = object()  # type: ignore
        checker.invalidate("foo.com")
        assert "foo.com" not in checker._cache
        assert "bar.com" in checker._cache

    @pytest.mark.asyncio
    async def test_can_fetch_invalid_url_allows(self):
        """URL غير صالح → يسمح بالـ crawl (fail-open)."""
        from data_engine.ingestion.crawlers.robots_checker import RobotsChecker
        checker = RobotsChecker()
        result = await checker.can_fetch("not_a_valid_url")
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightCrawlerConfig
# ─────────────────────────────────────────────────────────────────────────────

class TestPlaywrightCrawlerConfig:
    def test_defaults(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawlerConfig
        cfg = PlaywrightCrawlerConfig()
        assert cfg.headless is True
        assert cfg.timeout_ms == 30_000
        assert cfg.max_retries == 2
        assert cfg.requests_per_second == 1.0

    def test_custom(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawlerConfig
        cfg = PlaywrightCrawlerConfig(
            headless=False,
            timeout_ms=10_000,
            max_retries=5,
            requests_per_second=2.0,
        )
        assert cfg.headless is False
        assert cfg.timeout_ms == 10_000
        assert cfg.max_retries == 5

    def test_block_resources_default(self):
        from data_engine.ingestion.crawlers.playwright_crawler import PlaywrightCrawlerConfig
        cfg = PlaywrightCrawlerConfig()
        assert "image" in cfg.block_resources
        assert "font" in cfg.block_resources
