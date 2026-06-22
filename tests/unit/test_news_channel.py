"""Tests for NewsChannel — section 5.16."""
from __future__ import annotations
import pytest
from shared.schemas.article import Article, ArticleMetadata
from shared.schemas.channel import ChannelConfig, SourceConfig, ChannelStatus
from data_engine.channels.predefined.news_channel import NewsChannel
from data_engine.processing.filtering.policy_filter import PolicyFilterConfig
from shared.utils.datetime_utils import utc_now


def _make_channel_config() -> ChannelConfig:
    return ChannelConfig(
        id="news_ch_001",
        name="Test News Channel",
        status=ChannelStatus.ACTIVE,
        source=SourceConfig(
            url="https://example.com/feed",
            type="demo",
        ),
    )


def _make_article(aid: str = "art_001") -> Article:
    return Article(
        id=aid,
        title="Test Article",
        content=(
            "Artificial intelligence research is advancing rapidly worldwide. "
            "Machine learning enables computers to learn from large datasets. "
            "These technologies are transforming healthcare, education and industry."
        ),
        url="https://example.com/article",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="news_ch_001", language="en"),
    )


class TestNewsChannel:
    def setup_method(self):
        self.cfg = _make_channel_config()
        self.channel = NewsChannel(
            config=self.cfg,
            policy_config_path="configs/filters.yaml",
        )

    @pytest.mark.asyncio
    async def test_fetch_returns_articles(self):
        result = await self.channel.fetch()
        assert isinstance(result.articles, list)
        assert result.has_more is False
        assert "fetched_at" in result.metadata

    @pytest.mark.asyncio
    async def test_validate_source_returns_bool(self):
        valid = await self.channel.validate_source()
        assert isinstance(valid, bool)

    @pytest.mark.asyncio
    async def test_run_pipeline_with_articles(self):
        arts = [_make_article(aid=f"a_{i}") for i in range(3)]
        result = await self.channel.run_pipeline(articles=arts)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_pipeline_updates_counters(self):
        arts = [_make_article()]
        await self.channel.run_pipeline(articles=arts)
        assert self.channel.last_run is not None
        assert self.channel.total_fetched >= 0

    @pytest.mark.asyncio
    async def test_run_pipeline_no_articles_returns_empty(self):
        # Demo fetch returns articles, but we can override
        arts = []
        # Patch fetch to return empty
        original_fetch = self.channel.fetch
        async def empty_fetch(last_fetched_id=None):
            from data_engine.channels.base import FetchResult
            return FetchResult(articles=[], has_more=False, metadata={})
        self.channel.fetch = empty_fetch
        result = await self.channel.run_pipeline(articles=None)
        assert result == []
        self.channel.fetch = original_fetch

    @pytest.mark.asyncio
    async def test_full_cycle_fetch_and_process(self):
        """Full cycle: fetch → pipeline."""
        result = await self.channel.run_pipeline()
        assert isinstance(result, list)
        # Should have processed the demo articles
        assert self.channel.last_run is not None

    @pytest.mark.asyncio
    async def test_arabic_articles_processed(self):
        ar_art = Article(
            id="ar_news_001",
            title="الذكاء الاصطناعي",
            content=(
                "يُحدث الذكاء الاصطناعي ثورة حقيقية في جميع قطاعات الاقتصاد العالمي. "
                "تُمكّن خوارزميات التعلم الآلي الحواسيب من اكتشاف الأنماط في البيانات الضخمة."
            ),
            url="https://arabic-news.com/article",
            published_at=utc_now(),
            metadata=ArticleMetadata(source_id="news_ch_001", language="ar"),
        )
        result = await self.channel.run_pipeline(articles=[ar_art])
        assert isinstance(result, list)
