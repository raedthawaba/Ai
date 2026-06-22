import pytest
from datetime import datetime
from shared.schemas.channel import ChannelConfig, SourceConfig, ChannelStatus
from data_engine.channels.predefined.demo_channel import DemoChannel
from data_engine.channels.base import FetchResult


@pytest.fixture
def demo_channel_config():
    return ChannelConfig(
        id="test_demo_id",
        name="Test Demo Channel",
        status=ChannelStatus.ACTIVE,
        source=SourceConfig(
            url="https://example.com/demo",
            type="demo"
        )
    )


@pytest.mark.asyncio
async def test_demo_channel_fetch(demo_channel_config):
    channel = DemoChannel(config=demo_channel_config)
    result = await channel.fetch()
    
    assert isinstance(result, FetchResult)
    assert len(result.articles) == 2
    assert result.articles[0].id == "demo_art_001"
    assert result.articles[1].id == "demo_art_002"
    assert result.metadata["source_type"] == "demo"


@pytest.mark.asyncio
async def test_demo_channel_validate_source(demo_channel_config):
    channel = DemoChannel(config=demo_channel_config)
    is_valid = await channel.validate_source()
    assert is_valid is True


@pytest.mark.asyncio
async def test_demo_channel_validate_source_invalid(demo_channel_config):
    demo_channel_config.source.type = "rss"
    channel = DemoChannel(config=demo_channel_config)
    is_valid = await channel.validate_source()
    assert is_valid is False


@pytest.mark.asyncio
async def test_demo_channel_run_pipeline(demo_channel_config):
    channel = DemoChannel(config=demo_channel_config)
    result = await channel.fetch()
    processed_articles = await channel.run_pipeline(result.articles)
    
    assert len(processed_articles) == len(result.articles)
    assert processed_articles[0].id == result.articles[0].id
