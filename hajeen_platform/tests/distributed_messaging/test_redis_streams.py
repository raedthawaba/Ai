import pytest
import asyncio
from unittest.mock import MagicMock, patch
from hajeen_platform.services.distributed_messaging.redis_streams_integration import RedisStreamsClient

@pytest.fixture
def mock_redis_client():
    with patch("redis.Redis") as mock_redis:
        yield mock_redis.return_value

@pytest.mark.asyncio
async def test_redis_streams_client_init():
    with patch("redis.Redis") as mock_redis_constructor:
        client = RedisStreamsClient()
        mock_redis_constructor.assert_called_once_with(host="localhost", port=6379, db=0, decode_responses=True)
        assert client is not None

@pytest.mark.asyncio
async def test_add_message(mock_redis_client):
    client = RedisStreamsClient()
    stream_name = "test_stream"
    message_data = {"key": "value"}
    mock_redis_client.xadd.return_value = b"1678888888-0"

    message_id = await client.add_message(stream_name, message_data)
    mock_redis_client.xadd.assert_called_once_with(stream_name, message_data)
    assert message_id == b"1678888888-0"

@pytest.mark.asyncio
async def test_read_messages(mock_redis_client):
    client = RedisStreamsClient()
    stream_name = "test_stream"
    consumer_group = "test_group"
    consumer_name = "test_consumer"
    
    mock_redis_client.xreadgroup.return_value = [
        (b"test_stream", [
            (b"1678888888-0", {b"key": b"value1"}),
            (b"1678888888-1", {b"key": b"value2"})
        ])
    ]
    mock_redis_client.xgroup_create.side_effect = lambda *args, **kwargs: None # Mock successful creation or busygroup

    messages = await client.read_messages(stream_name, consumer_group, consumer_name)
    mock_redis_client.xgroup_create.assert_called_once()
    mock_redis_client.xreadgroup.assert_called_once_with(
        consumer_group, consumer_name, {stream_name: ">"}, count=10, block=5000
    )
    mock_redis_client.xack.assert_any_call(stream_name, consumer_group, b"1678888888-0")
    mock_redis_client.xack.assert_any_call(stream_name, consumer_group, b"1678888888-1")
    assert len(messages) == 2
    assert messages[0]["id"] == b"1678888888-0"
    assert messages[0]["data"] == {b"key": b"value1"}
