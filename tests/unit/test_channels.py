import pytest
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from data_engine.channels.base import BaseChannel, FetchResult
from shared.schemas.article import Article
from shared.schemas.channel import ChannelConfig, ChannelStatus, SourceConfig
from shared.schemas.article import ArticleMetadata
from shared.exceptions import ChannelException


class ConcreteChannel(BaseChannel):
    """A concrete implementation of BaseChannel for testing purposes."""
    async def fetch(self, last_fetched_id: Optional[str] = None) -> FetchResult:
        return FetchResult(articles=[], has_more=False)

    async def validate_source(self) -> bool:
        return True


def test_fetch_result_model():
    result = FetchResult(articles=[], metadata={"key": "value"}, has_more=True)
    assert isinstance(result, FetchResult)
    assert result.articles == []
    assert result.metadata == {"key": "value"}
    assert result.has_more is True

    # Test with invalid input for articles (should raise ValidationError)
    with pytest.raises(Exception): # Pydantic v2 raises pydantic_core._pydantic_core.ValidationError
        FetchResult(articles="not a list")


@pytest.mark.asyncio
async def test_base_channel_initialization():
    source_config = SourceConfig(url="https://example.com/feed", type="RSS")
    config = ChannelConfig(id="test_channel_1", name="Test Channel", type="RSS", source=source_config, status=ChannelStatus.ACTIVE)
    channel = ConcreteChannel(config=config)
    assert channel.config == config
    assert channel.get_status() == ChannelStatus.ACTIVE


@pytest.mark.asyncio
async def test_base_channel_fetch():
    source_config = SourceConfig(url="https://example.com/feed", type="RSS")
    config = ChannelConfig(id="test_channel_2", name="Test Channel", type="RSS", source=source_config)
    channel = ConcreteChannel(config=config)
    fetch_result = await channel.fetch()
    assert isinstance(fetch_result, FetchResult)
    assert fetch_result.articles == []
    assert fetch_result.has_more is False


@pytest.mark.asyncio
async def test_base_channel_validate_source():
    source_config = SourceConfig(url="https://example.com/feed", type="RSS")
    config = ChannelConfig(id="test_channel_3", name="Test Channel", type="RSS", source=source_config)
    channel = ConcreteChannel(config=config)
    is_valid = await channel.validate_source()
    assert is_valid is True


@pytest.mark.asyncio
async def test_base_channel_run_pipeline():
    source_config = SourceConfig(url="https://example.com/feed", type="RSS")
    config = ChannelConfig(id="test_channel_4", name="Test Channel", type="RSS", source=source_config)
    channel = ConcreteChannel(config=config)
    from datetime import datetime, timezone
    article = Article(id="art1", title="Test Article", url="https://example.com/article1", content="content", published_at=datetime.now(timezone.utc), metadata=ArticleMetadata(source_id="test_source"))
    articles = [article]
    processed_articles = await channel.run_pipeline(articles)
    assert processed_articles == articles


@pytest.mark.asyncio
async def test_base_channel_status_update():
    source_config = SourceConfig(url="https://example.com/feed", type="RSS")
    config = ChannelConfig(id="test_channel_5", name="Test Channel", type="RSS", source=source_config, status=ChannelStatus.DRAFT)
    channel = ConcreteChannel(config=config)
    assert channel.get_status() == ChannelStatus.DRAFT
    channel.update_status(ChannelStatus.ACTIVE)
    assert channel.get_status() == ChannelStatus.ACTIVE


@pytest.mark.asyncio
async def test_base_channel_context_manager():
    source_config = SourceConfig(url="https://example.com/feed", type="RSS")
    config = ChannelConfig(id="test_channel_6", name="Test Channel", type="RSS", source=source_config)
    channel = ConcreteChannel(config=config)
    async with channel as ch:
        assert ch == channel
        # No specific actions to test inside, just ensuring it enters and exits without error
