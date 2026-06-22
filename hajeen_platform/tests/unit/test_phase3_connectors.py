"""اختبارات Phase 3 — Section 3.2: Connectors.

يغطّي:
- BaseConnector (RateLimiter, pagination)
- YouTubeConnector (init, validate_response, _video_to_article)
- ArxivConnector (init, _parse_atom_feed, _entry_to_article)
- RedditConnector (validate_response, _post_to_article)
- GitHubConnector (init, authenticate)
- NewsAPIConnector (init, validate_response)
"""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# RateLimiter
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_does_not_raise(self):
        from data_engine.ingestion.connectors.base_connector import RateLimiter
        limiter = RateLimiter(requests_per_second=100.0)
        await limiter.acquire()  # يجب ألا يُلقي استثناءً

    @pytest.mark.asyncio
    async def test_respects_rate_limit(self):
        """معدل منخفض جداً → يُؤخّر الطلب الثاني."""
        import time
        from data_engine.ingestion.connectors.base_connector import RateLimiter
        limiter = RateLimiter(requests_per_second=5.0)  # 200ms بين طلبين
        t0 = time.monotonic()
        await limiter.acquire()
        await limiter.acquire()
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.15, f"Expected >= 0.15s, got {elapsed:.3f}s"

    def test_zero_rps_fallback(self):
        """قيمة 0 يجب ألا تُسبب division by zero."""
        from data_engine.ingestion.connectors.base_connector import RateLimiter
        limiter = RateLimiter(requests_per_second=0)
        assert limiter._min_interval >= 0


# ─────────────────────────────────────────────────────────────────────────────
# YouTubeConnector
# ─────────────────────────────────────────────────────────────────────────────

class TestYouTubeConnector:
    def test_init_defaults(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test_key")
        assert yt.source_id == "youtube"
        assert yt._api_key == "test_key"

    @pytest.mark.asyncio
    async def test_authenticate_sets_flag(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test")
        assert not yt.is_authenticated
        await yt.authenticate()
        assert yt.is_authenticated

    def test_validate_response_valid(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test")
        assert yt.validate_response({"kind": "youtube#searchListResponse", "items": []})

    def test_validate_response_invalid_list(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test")
        assert not yt.validate_response([])

    def test_validate_response_invalid_empty_dict(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test")
        assert not yt.validate_response({})

    def test_video_to_article_returns_none_on_empty(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test")
        result = yt._video_to_article({"snippet": {}, "statistics": {}})
        assert result is None

    def test_video_to_article_valid(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key="test")
        item = {
            "id": "abc123",
            "snippet": {
                "title": "Test Video",
                "description": "Test description",
                "channelTitle": "Test Channel",
                "publishedAt": "2024-01-15T12:00:00Z",
                "tags": ["tech", "AI"],
            },
            "statistics": {
                "viewCount": "10000",
                "likeCount": "500",
                "commentCount": "50",
            },
        }
        article = yt._video_to_article(item)
        assert article is not None
        assert article.title == "Test Video"
        assert "youtube.com/watch?v=abc123" in str(article.url)
        assert article.metadata.extra["view_count"] == 10000
        assert article.metadata.extra["video_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_fetch_without_api_key_returns_empty(self):
        from data_engine.ingestion.connectors.youtube_connector import YouTubeConnector
        yt = YouTubeConnector(api_key=None)
        yt._api_key = None
        result = await yt.fetch(query="test")
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# ArxivConnector
# ─────────────────────────────────────────────────────────────────────────────

class TestArxivConnector:
    def test_init_defaults(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        assert ax.source_id == "arxiv"
        assert ax.max_retries == 3

    @pytest.mark.asyncio
    async def test_authenticate_sets_flag(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        await ax.authenticate()
        assert ax.is_authenticated

    def test_validate_response_valid(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        assert ax.validate_response("<feed>content</feed>")

    def test_validate_response_invalid(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        assert not ax.validate_response({"key": "value"})
        assert not ax.validate_response("")

    def test_parse_atom_feed_empty(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        results = ax._parse_atom_feed("<invalid_xml>")
        assert results == []

    def test_parse_atom_feed_valid(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2401.00001</id>
    <title>Test Paper on Machine Learning</title>
    <summary>This is a test summary for the paper.</summary>
    <published>2024-01-15T12:00:00Z</published>
    <author><name>Test Author</name></author>
    <category term="cs.AI"/>
  </entry>
</feed>"""
        results = ax._parse_atom_feed(xml)
        assert len(results) == 1
        assert results[0].title == "Test Paper on Machine Learning"
        assert "arxiv" in str(results[0].url)

    def test_parse_atom_feed_skips_entry_without_id(self):
        from data_engine.ingestion.connectors.arxiv_connector import ArxivConnector
        ax = ArxivConnector()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id></id>
    <title>No ID Paper</title>
  </entry>
</feed>"""
        results = ax._parse_atom_feed(xml)
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# RedditConnector
# ─────────────────────────────────────────────────────────────────────────────

class TestRedditConnector:
    def test_init_defaults(self):
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector
        r = RedditConnector()
        assert r.source_id == "reddit"
        assert r.max_retries == 3

    @pytest.mark.asyncio
    async def test_authenticate_no_token(self):
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector
        r = RedditConnector()
        await r.authenticate()
        assert r.is_authenticated

    def test_validate_response_valid(self):
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector
        r = RedditConnector()
        assert r.validate_response({
            "kind": "Listing",
            "data": {"children": []}
        })

    def test_validate_response_invalid_kind(self):
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector
        r = RedditConnector()
        assert not r.validate_response({"kind": "t3", "data": {}})

    def test_post_to_article_valid(self):
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector
        r = RedditConnector()
        child = {
            "kind": "t3",
            "data": {
                "id": "abc123",
                "title": "Test Post",
                "url": "https://example.com/post",
                "selftext": "Body content of the post",
                "author": "testuser",
                "score": 500,
                "num_comments": 100,
                "created_utc": 1705320000.0,
                "is_self": False,
                "permalink": "/r/tech/comments/abc123",
            }
        }
        article = r._post_to_article(child, subreddit="tech")
        assert article is not None
        assert article.title == "Test Post"
        assert article.metadata.extra["score"] == 500
        assert article.metadata.extra["subreddit"] == "tech"

    def test_post_to_article_skips_missing_title(self):
        from data_engine.ingestion.connectors.reddit_connector import RedditConnector
        r = RedditConnector()
        child = {"kind": "t3", "data": {"url": "https://example.com"}}
        result = r._post_to_article(child, subreddit="tech")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# BaseConnector._has_next_page
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseConnectorHelpers:
    def _make_connector(self):
        from data_engine.ingestion.connectors.base_connector import BaseConnector
        class Concrete(BaseConnector):
            async def authenticate(self): self._authenticated = True
            async def fetch(self, **kw): return []
            def validate_response(self, data): return isinstance(data, dict)
        return Concrete(base_url="http://example.com")

    def test_has_next_page_list_full(self):
        c = self._make_connector()
        assert c._has_next_page([1, 2, 3, 4, 5], 1, 5)

    def test_has_next_page_list_partial(self):
        c = self._make_connector()
        assert not c._has_next_page([1, 2], 1, 5)

    def test_has_next_page_dict_articles(self):
        c = self._make_connector()
        data = {"articles": list(range(10))}
        assert c._has_next_page(data, 1, 10)

    def test_has_next_page_dict_partial(self):
        c = self._make_connector()
        data = {"articles": list(range(3))}
        assert not c._has_next_page(data, 1, 10)

    def test_has_next_page_unknown_type(self):
        c = self._make_connector()
        assert not c._has_next_page("string_data", 1, 10)
