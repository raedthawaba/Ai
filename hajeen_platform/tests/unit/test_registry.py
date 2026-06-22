import pytest
from data_engine.channels.registry import ChannelRegistry
from data_engine.channels.base import BaseChannel, FetchResult
from shared.schemas.channel import ChannelConfig, ChannelStatus, SourceConfig
from shared.exceptions import ChannelException
from typing import Optional


class DummyChannel(BaseChannel):
    """Concrete implementation of BaseChannel for registry tests."""

    async def fetch(self, last_fetched_id: Optional[str] = None) -> FetchResult:
        return FetchResult(articles=[], has_more=False)

    async def validate_source(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clear_registry_after_each_test():
    """Ensure the registry is clean before and after each test."""
    ChannelRegistry.clear()
    yield
    ChannelRegistry.clear()


def create_test_channel(channel_id: str, name: str) -> DummyChannel:
    source_config = SourceConfig(url=f"https://example.com/{name}", type="RSS")
    config = ChannelConfig(
        id=channel_id,
        name=name,
        type="RSS",
        source=source_config,
        status=ChannelStatus.DRAFT,
    )
    return DummyChannel(config=config)


def test_register_channel():
    channel = create_test_channel("ch_1", "Channel One")
    ChannelRegistry.register(channel)
    assert ChannelRegistry.get("ch_1") == channel
    assert len(ChannelRegistry.list_all()) == 1


def test_register_duplicate_channel_raises_exception():
    channel = create_test_channel("ch_1", "Channel One")
    ChannelRegistry.register(channel)
    with pytest.raises(ChannelException, match="already registered"):
        ChannelRegistry.register(channel)


def test_register_invalid_object_raises_exception():
    with pytest.raises(ChannelException, match="Invalid channel object"):
        ChannelRegistry.register("not_a_channel")


def test_unregister_channel():
    channel = create_test_channel("ch_2", "Channel Two")
    ChannelRegistry.register(channel)
    assert ChannelRegistry.get("ch_2") is not None
    ChannelRegistry.unregister("ch_2")
    assert ChannelRegistry.get("ch_2") is None
    assert len(ChannelRegistry.list_all()) == 0


def test_unregister_non_existent_channel_raises_exception():
    with pytest.raises(ChannelException, match="not found for unregistration"):
        ChannelRegistry.unregister("non_existent_channel")


def test_get_channel():
    channel = create_test_channel("ch_3", "Channel Three")
    ChannelRegistry.register(channel)
    retrieved_channel = ChannelRegistry.get("ch_3")
    assert retrieved_channel == channel


def test_get_non_existent_channel_returns_none():
    assert ChannelRegistry.get("ch_non_existent") is None


def test_list_all_channels():
    channel1 = create_test_channel("ch_4", "Channel Four")
    channel2 = create_test_channel("ch_5", "Channel Five")
    ChannelRegistry.register(channel1)
    ChannelRegistry.register(channel2)
    all_channels = ChannelRegistry.list_all()
    assert len(all_channels) == 2
    assert channel1 in all_channels
    assert channel2 in all_channels


def test_update_channel_status():
    channel = create_test_channel("ch_6", "Channel Six")
    ChannelRegistry.register(channel)
    assert ChannelRegistry.get("ch_6").get_status() == ChannelStatus.DRAFT
    ChannelRegistry.update_status("ch_6", ChannelStatus.ACTIVE)
    assert ChannelRegistry.get("ch_6").get_status() == ChannelStatus.ACTIVE


def test_update_status_non_existent_channel_raises_exception():
    with pytest.raises(ChannelException, match="not found for status update"):
        ChannelRegistry.update_status("ch_non_existent", ChannelStatus.ACTIVE)


def test_clear_registry():
    channel = create_test_channel("ch_7", "Channel Seven")
    ChannelRegistry.register(channel)
    assert len(ChannelRegistry.list_all()) == 1
    ChannelRegistry.clear()
    assert len(ChannelRegistry.list_all()) == 0
