"""اختبارات Phase 3 — Section 3.5: Channels.

يغطّي:
- TechChannel (init, validate_source mock, add/remove feeds)
- ScienceChannel (init, config)
- FinanceChannel (init, config, subreddits)
- ChannelRegistry (register, unregister, get, list)
- FetchResult
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_channel_config(
    channel_id: str = "test_channel",
    name: str = "Test Channel",
    source_config: dict = None,
):
    """إنشاء ChannelConfig للاختبار."""
    from shared.schemas.channel import ChannelConfig, SourceConfig
    return ChannelConfig(
        id=channel_id,
        name=name,
        source=SourceConfig(
            url="http://example-source.com",
            type="rss",
            params=source_config or {},
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# FetchResult
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchResult:
    def test_empty_result(self):
        from data_engine.channels.base import FetchResult
        result = FetchResult()
        assert result.articles == []
        assert result.metadata == {}
        assert result.has_more is False

    def test_with_articles(self):
        from data_engine.channels.base import FetchResult
        from shared.schemas.article import Article, ArticleMetadata
        article = Article(
            id="art_test_fetch",
            title="Test Article",
            content="Test content body",
            url="http://example.com/test",  # type: ignore[arg-type]
            published_at=datetime.now(timezone.utc),
            metadata=ArticleMetadata(source_id="test", language="en"),
        )
        result = FetchResult(
            articles=[article],
            metadata={"channel": "tech"},
            has_more=True,
        )
        assert len(result.articles) == 1
        assert result.has_more is True


# ─────────────────────────────────────────────────────────────────────────────
# TechChannel
# ─────────────────────────────────────────────────────────────────────────────

class TestTechChannel:
    def test_init_defaults(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config("tech_001", "Tech Channel")
        ch = TechChannel(config=cfg)
        assert ch.config.id == "tech_001"
        assert len(ch._feeds) > 0
        assert ch._max_per_feed == 20
        assert ch._check_robots is True

    def test_init_custom_feeds(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config(source_config={
            "rss_feeds": ["http://feed1.com", "http://feed2.com"],
            "max_articles_per_feed": 5,
        })
        ch = TechChannel(config=cfg)
        assert len(ch._feeds) == 2
        assert ch._max_per_feed == 5

    def test_add_feed(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config()
        ch = TechChannel(config=cfg)
        initial_count = len(ch._feeds)
        ch.add_feed("http://new.feed.com/rss")
        assert len(ch._feeds) == initial_count + 1
        assert "http://new.feed.com/rss" in ch.feed_urls

    def test_add_feed_no_duplicate(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config()
        ch = TechChannel(config=cfg)
        ch.add_feed("http://unique.feed.com")
        ch.add_feed("http://unique.feed.com")  # مُكرّر
        assert ch._feeds.count("http://unique.feed.com") == 1

    def test_remove_feed(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config(source_config={
            "rss_feeds": ["http://a.com", "http://b.com"]
        })
        ch = TechChannel(config=cfg)
        result = ch.remove_feed("http://a.com")
        assert result is True
        assert "http://a.com" not in ch._feeds

    def test_remove_nonexistent_feed(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config()
        ch = TechChannel(config=cfg)
        result = ch.remove_feed("http://nonexistent.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_with_mocked_rss(self):
        from data_engine.channels.predefined.tech_channel import TechChannel
        from shared.schemas.article import Article, ArticleMetadata

        cfg = _make_channel_config(source_config={
            "rss_feeds": ["http://test.feed.com"],
            "check_robots": False,
        })
        ch = TechChannel(config=cfg)

        # Mock article
        mock_article = Article(
            id="art_test001",
            title="Test Article",
            content="Test content body text",
            url="http://example.com/article",  # type: ignore[arg-type]
            published_at=datetime.now(timezone.utc),
            metadata=ArticleMetadata(source_id="test", language="en"),
        )

        with patch(
            "data_engine.channels.predefined.tech_channel.parse_rss_feed",
            return_value=[mock_article],
        ):
            result = await ch.fetch()

        assert len(result.articles) == 1
        assert result.articles[0].title == "Test Article"
        assert result.metadata["channel"] == "tech"

    @pytest.mark.asyncio
    async def test_fetch_handles_feed_error(self):
        from data_engine.channels.predefined.tech_channel import TechChannel

        cfg = _make_channel_config(source_config={
            "rss_feeds": ["http://broken.feed.com"],
            "check_robots": False,
        })
        ch = TechChannel(config=cfg)

        with patch(
            "data_engine.channels.predefined.tech_channel.parse_rss_feed",
            side_effect=Exception("Connection refused"),
        ):
            result = await ch.fetch()

        # يجب ألا يُلقي استثناءً — يُعيد قائمة فارغة
        assert result.articles == []

    @pytest.mark.asyncio
    async def test_validate_source_with_mock(self):
        from data_engine.channels.predefined.tech_channel import TechChannel

        cfg = _make_channel_config()
        ch = TechChannel(config=cfg)

        with patch(
            "data_engine.channels.predefined.tech_channel.validate_rss_feed",
            return_value=True,
        ):
            valid = await ch.validate_source()

        assert valid is True

    @pytest.mark.asyncio
    async def test_validate_source_all_invalid(self):
        from data_engine.channels.predefined.tech_channel import TechChannel

        cfg = _make_channel_config()
        ch = TechChannel(config=cfg)

        with patch(
            "data_engine.channels.predefined.tech_channel.validate_rss_feed",
            return_value=False,
        ):
            valid = await ch.validate_source()

        assert valid is False


# ─────────────────────────────────────────────────────────────────────────────
# ScienceChannel
# ─────────────────────────────────────────────────────────────────────────────

class TestScienceChannel:
    def test_init_defaults(self):
        from data_engine.channels.predefined.science_channel import ScienceChannel
        cfg = _make_channel_config("sci_001", "Science Channel")
        ch = ScienceChannel(config=cfg)
        assert len(ch._feeds) > 0
        assert len(ch._arxiv_categories) > 0
        assert ch._include_arxiv is True
        assert ch._arxiv_max == 10

    def test_init_custom(self):
        from data_engine.channels.predefined.science_channel import ScienceChannel
        cfg = _make_channel_config(source_config={
            "arxiv_categories": ["cs.AI", "cs.LG"],
            "arxiv_max_per_category": 5,
            "include_arxiv": False,
        })
        ch = ScienceChannel(config=cfg)
        assert ch._arxiv_categories == ["cs.AI", "cs.LG"]
        assert ch._arxiv_max == 5
        assert ch._include_arxiv is False

    @pytest.mark.asyncio
    async def test_fetch_without_arxiv(self):
        from data_engine.channels.predefined.science_channel import ScienceChannel

        cfg = _make_channel_config(source_config={
            "rss_feeds": ["http://science.feed.com"],
            "include_arxiv": False,
            "check_robots": False,
        })
        ch = ScienceChannel(config=cfg)

        with patch(
            "data_engine.channels.predefined.science_channel.parse_rss_feed",
            return_value=[],
        ):
            result = await ch.fetch()

        assert result.articles == []
        assert result.metadata["channel"] == "science"
        assert "arxiv_stats" not in result.metadata


# ─────────────────────────────────────────────────────────────────────────────
# FinanceChannel
# ─────────────────────────────────────────────────────────────────────────────

class TestFinanceChannel:
    def test_init_defaults(self):
        from data_engine.channels.predefined.finance_channel import FinanceChannel
        cfg = _make_channel_config("fin_001", "Finance Channel")
        ch = FinanceChannel(config=cfg)
        assert len(ch._feeds) > 0
        assert len(ch._subreddits) > 0
        assert ch._include_reddit is True

    def test_init_no_reddit(self):
        from data_engine.channels.predefined.finance_channel import FinanceChannel
        cfg = _make_channel_config(source_config={"include_reddit": False})
        ch = FinanceChannel(config=cfg)
        assert ch._include_reddit is False

    def test_custom_subreddits(self):
        from data_engine.channels.predefined.finance_channel import FinanceChannel
        cfg = _make_channel_config(source_config={
            "subreddits": ["wallstreetbets", "CryptoCurrency"],
        })
        ch = FinanceChannel(config=cfg)
        assert "wallstreetbets" in ch._subreddits

    @pytest.mark.asyncio
    async def test_fetch_without_reddit(self):
        from data_engine.channels.predefined.finance_channel import FinanceChannel

        cfg = _make_channel_config(source_config={
            "rss_feeds": ["http://finance.feed.com"],
            "include_reddit": False,
            "check_robots": False,
        })
        ch = FinanceChannel(config=cfg)

        with patch(
            "data_engine.channels.predefined.finance_channel.parse_rss_feed",
            return_value=[],
        ):
            result = await ch.fetch()

        assert result.articles == []
        assert result.metadata["channel"] == "finance"
        assert "reddit_stats" not in result.metadata


# ─────────────────────────────────────────────────────────────────────────────
# ChannelRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelRegistry:
    def setup_method(self):
        """مسح الـ registry قبل كل اختبار."""
        from data_engine.channels.registry import ChannelRegistry
        ChannelRegistry.clear()

    def _make_tech_channel(self, channel_id="reg_tech_001"):
        from data_engine.channels.predefined.tech_channel import TechChannel
        cfg = _make_channel_config(channel_id, f"Channel {channel_id}")
        return TechChannel(config=cfg)

    def test_register_and_get(self):
        from data_engine.channels.registry import ChannelRegistry

        with patch("data_engine.channels.registry._save_channel_to_db"):
            with patch("data_engine.channels.registry._ensure_db"):
                ch = self._make_tech_channel("reg_001")
                ChannelRegistry.register(ch)
                retrieved = ChannelRegistry.get("reg_001")
                assert retrieved is ch

    def test_register_duplicate_raises(self):
        from data_engine.channels.registry import ChannelRegistry
        from shared.exceptions import ChannelException

        with patch("data_engine.channels.registry._save_channel_to_db"):
            with patch("data_engine.channels.registry._ensure_db"):
                ch = self._make_tech_channel("dup_001")
                ChannelRegistry.register(ch)
                with pytest.raises(ChannelException):
                    ChannelRegistry.register(ch)

    def test_unregister(self):
        from data_engine.channels.registry import ChannelRegistry

        with patch("data_engine.channels.registry._save_channel_to_db"):
            with patch("data_engine.channels.registry._ensure_db"):
                with patch("data_engine.channels.registry._delete_channel_from_db"):
                    ch = self._make_tech_channel("unreg_001")
                    ChannelRegistry.register(ch)
                    ChannelRegistry.unregister("unreg_001")
                    assert ChannelRegistry.get("unreg_001") is None

    def test_unregister_nonexistent_raises(self):
        from data_engine.channels.registry import ChannelRegistry
        from shared.exceptions import ChannelException

        with pytest.raises(ChannelException):
            ChannelRegistry.unregister("ghost_channel")

    def test_get_nonexistent_returns_none(self):
        from data_engine.channels.registry import ChannelRegistry
        assert ChannelRegistry.get("nonexistent") is None

    def test_count(self):
        from data_engine.channels.registry import ChannelRegistry

        with patch("data_engine.channels.registry._save_channel_to_db"):
            with patch("data_engine.channels.registry._ensure_db"):
                ch1 = self._make_tech_channel("count_001")
                ch2 = self._make_tech_channel("count_002")
                ChannelRegistry.register(ch1)
                ChannelRegistry.register(ch2)
                assert ChannelRegistry.count() == 2

    def test_list_all(self):
        from data_engine.channels.registry import ChannelRegistry

        with patch("data_engine.channels.registry._save_channel_to_db"):
            with patch("data_engine.channels.registry._ensure_db"):
                ch1 = self._make_tech_channel("list_001")
                ch2 = self._make_tech_channel("list_002")
                ChannelRegistry.register(ch1)
                ChannelRegistry.register(ch2)
                channels = ChannelRegistry.list_all()
                assert len(channels) == 2

    def test_clear(self):
        from data_engine.channels.registry import ChannelRegistry

        with patch("data_engine.channels.registry._save_channel_to_db"):
            with patch("data_engine.channels.registry._ensure_db"):
                ch = self._make_tech_channel("clear_001")
                ChannelRegistry.register(ch)
        ChannelRegistry.clear()
        assert ChannelRegistry.count() == 0
