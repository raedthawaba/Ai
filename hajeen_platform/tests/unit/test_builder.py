import pytest
from data_engine.channels.builder import ChannelBuilder, RSSChannel, APIChannel, PlaceholderChannel
from data_engine.channels.base import BaseChannel, FetchResult
from shared.schemas.channel import ChannelConfig, ChannelStatus, SourceConfig
from shared.schemas.article import Article
from shared.exceptions import ChannelException, ValidationException
from typing import Optional, List, Dict, Any
from pydantic import HttpUrl


# Helper function to create a basic ChannelConfig
def create_mock_channel_config(channel_id: str, name: str, source_type: str, url: str = "https://example.com") -> ChannelConfig:
    source_config = SourceConfig(url=HttpUrl(url), type=source_type)
    return ChannelConfig(id=channel_id, name=name, source=source_config, status=ChannelStatus.DRAFT)


# Test ChannelBuilder.create()
@pytest.mark.asyncio
async def test_create_rss_channel():
    config = create_mock_channel_config("rss_ch_1", "RSS Test Channel", "RSS")
    channel = await ChannelBuilder.create("rss", config)
    assert isinstance(channel, RSSChannel)
    assert channel.config == config


@pytest.mark.asyncio
async def test_create_api_channel():
    config = create_mock_channel_config("api_ch_1", "API Test Channel", "API")
    channel = await ChannelBuilder.create("api", config)
    assert isinstance(channel, APIChannel)
    assert channel.config == config


@pytest.mark.asyncio
async def test_create_placeholder_channel():
    config = create_mock_channel_config("ph_ch_1", "Placeholder Test Channel", "Placeholder")
    channel = await ChannelBuilder.create("placeholder", config)
    assert isinstance(channel, PlaceholderChannel)
    assert channel.config == config


@pytest.mark.asyncio
async def test_create_unknown_channel_type_raises_exception():
    config = create_mock_channel_config("unknown_ch", "Unknown Channel", "Unknown")
    with pytest.raises(ChannelException, match="Unknown channel type"):
        await ChannelBuilder.create("unknown", config)


# Test ChannelBuilder.create_from_config()
@pytest.mark.asyncio
async def test_create_from_config_rss():
    config = create_mock_channel_config("rss_ch_2", "RSS Config Channel", "RSS")
    channel = await ChannelBuilder.create_from_config(config)
    assert isinstance(channel, RSSChannel)
    assert channel.config == config


@pytest.mark.asyncio
async def test_create_from_config_api():
    config = create_mock_channel_config("api_ch_2", "API Config Channel", "API")
    channel = await ChannelBuilder.create_from_config(config)
    assert isinstance(channel, APIChannel)
    assert channel.config == config


@pytest.mark.asyncio
async def test_create_from_config_invalid_object_raises_exception():
    with pytest.raises(ValidationException, match="Input must be a ChannelConfig object."):
        await ChannelBuilder.create_from_config({"id": "invalid"})


# Test ChannelBuilder.validate_config()
@pytest.mark.asyncio
async def test_validate_config_valid_rss():
    config = create_mock_channel_config("valid_rss", "Valid RSS", "RSS")
    assert await ChannelBuilder.validate_config(config) is True


@pytest.mark.asyncio
async def test_validate_config_valid_api():
    config = create_mock_channel_config("valid_api", "Valid API", "API")
    assert await ChannelBuilder.validate_config(config) is True


@pytest.mark.asyncio
async def test_validate_config_invalid_type_in_source_config_raises_exception():
    config = create_mock_channel_config("invalid_source_type", "Invalid Source Type", "NOT_A_TYPE")
    with pytest.raises(ValidationException, match="Unsupported channel type in config"):
        await ChannelBuilder.validate_config(config)


@pytest.mark.asyncio
async def test_validate_config_invalid_object_raises_exception():
    with pytest.raises(ValidationException, match="Input must be a ChannelConfig object."):
        await ChannelBuilder.validate_config("not_a_config")


# Test ChannelBuilder.register_channel_type()
@pytest.mark.asyncio
async def test_register_custom_channel_type():
    class CustomChannel(BaseChannel):
        async def fetch(self, last_fetched_id: str | None = None) -> FetchResult:
            return FetchResult(articles=[], has_more=False)

        async def validate_source(self) -> bool:
            return True

    ChannelBuilder.register_channel_type("custom", CustomChannel)
    config = create_mock_channel_config("custom_ch_1", "Custom Channel", "Custom")
    channel = await ChannelBuilder.create("custom", config)
    assert isinstance(channel, CustomChannel)


@pytest.mark.asyncio
async def test_register_invalid_channel_class_raises_exception():
    class NotAChannel:
        pass

    with pytest.raises(ChannelException, match="Registered channel class must inherit from BaseChannel."):
        ChannelBuilder.register_channel_type("invalid", NotAChannel)


# Test channel-specific validation within builder
@pytest.mark.asyncio
async def test_builder_channel_specific_validation_failure():
    # Create a config that is valid for ChannelConfig but invalid for RSSChannel's internal validation
    # For example, if RSSChannel's validate_source checked for a specific URL format
    class MalformedRSSChannel(RSSChannel):
        async def validate_source(self) -> bool:
            raise ValidationException("Malformed RSS URL")

    ChannelBuilder.register_channel_type("malformed_rss", MalformedRSSChannel)
    config = create_mock_channel_config("malformed_rss_ch", "Malformed RSS", "Malformed_RSS", url="https://valid.url")

    with pytest.raises(ValidationException, match="Channel-specific validation failed for type malformed_rss: Malformed RSS URL"):
        await ChannelBuilder.create("malformed_rss", config)

    # Unregister the custom channel type to avoid interference with other tests
    del ChannelBuilder._channel_types["malformed_rss"]
