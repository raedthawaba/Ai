"""اختبارات Phase 3 — Section 3.3: Streams.

يغطّي:
- WebSocketConfig
- WebhookReceiver (receive, HMAC verification, buffer, DLQ)
- KafkaConsumerConfig
- KafkaMessage
- verify_hmac_sha256
- StreamMessage
"""
from __future__ import annotations

import asyncio
import json
import pytest
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────────────────────────────

class TestWebSocketConfig:
    def test_defaults(self):
        from data_engine.ingestion.streams.websocket_listener import WebSocketConfig
        cfg = WebSocketConfig(url="ws://example.com/feed")
        assert cfg.reconnect_delay_s == 1.0
        assert cfg.max_reconnect_delay_s == 60.0
        assert cfg.buffer_size == 1000
        assert cfg.dead_letter_max == 100

    def test_custom(self):
        from data_engine.ingestion.streams.websocket_listener import WebSocketConfig
        cfg = WebSocketConfig(
            url="wss://feed.example.com",
            name="test_feed",
            reconnect_delay_s=2.0,
            buffer_size=500,
        )
        assert cfg.name == "test_feed"
        assert cfg.reconnect_delay_s == 2.0
        assert cfg.buffer_size == 500


class TestStreamMessage:
    def test_is_json_with_dict(self):
        from data_engine.ingestion.streams.websocket_listener import StreamMessage
        msg = StreamMessage(raw='{"key": "value"}', data={"key": "value"})
        assert msg.is_json()

    def test_is_json_false_for_none(self):
        from data_engine.ingestion.streams.websocket_listener import StreamMessage
        msg = StreamMessage(raw="not json", data=None)
        assert not msg.is_json()

    def test_is_json_false_for_string(self):
        from data_engine.ingestion.streams.websocket_listener import StreamMessage
        msg = StreamMessage(raw='"string"', data="string")
        assert not msg.is_json()

    def test_received_at_is_utc(self):
        from data_engine.ingestion.streams.websocket_listener import StreamMessage
        msg = StreamMessage(raw="test")
        assert msg.received_at.tzinfo is not None


class TestStreamMetrics:
    def test_defaults(self):
        from data_engine.ingestion.streams.websocket_listener import StreamMetrics
        m = StreamMetrics()
        assert m.total_messages == 0
        assert m.is_connected is False

    def test_to_dict(self):
        from data_engine.ingestion.streams.websocket_listener import StreamMetrics
        m = StreamMetrics(total_messages=10, valid_messages=8, is_connected=True)
        d = m.to_dict()
        assert d["total_messages"] == 10
        assert d["valid_messages"] == 8
        assert d["is_connected"] is True


class TestWebSocketListenerInit:
    def test_init(self):
        from data_engine.ingestion.streams.websocket_listener import (
            WebSocketListener, WebSocketConfig
        )
        cfg = WebSocketConfig(url="ws://example.com")
        listener = WebSocketListener(config=cfg)
        assert not listener._running
        assert not listener._connected

    def test_get_metrics_not_started(self):
        from data_engine.ingestion.streams.websocket_listener import (
            WebSocketListener, WebSocketConfig
        )
        cfg = WebSocketConfig(url="ws://example.com")
        listener = WebSocketListener(config=cfg)
        metrics = listener.get_metrics()
        assert metrics.total_messages == 0

    def test_dead_letter_empty_initially(self):
        from data_engine.ingestion.streams.websocket_listener import (
            WebSocketListener, WebSocketConfig
        )
        cfg = WebSocketConfig(url="ws://example.com")
        listener = WebSocketListener(config=cfg)
        assert listener.get_dead_letter_queue() == []

    def test_clear_dead_letter(self):
        from data_engine.ingestion.streams.websocket_listener import (
            WebSocketListener, WebSocketConfig, StreamMessage
        )
        cfg = WebSocketConfig(url="ws://example.com")
        listener = WebSocketListener(config=cfg)
        # Manually add to DLQ
        listener._dead_letter.append(StreamMessage(raw="bad"))
        listener.metrics.dead_letter_size = 1
        listener.clear_dead_letter_queue()
        assert listener.get_dead_letter_queue() == []
        assert listener.metrics.dead_letter_size == 0


# ─────────────────────────────────────────────────────────────────────────────
# HMAC Verification
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyHMAC:
    def test_valid_signature(self):
        import hashlib, hmac as hmac_lib
        from data_engine.ingestion.streams.webhook_receiver import verify_hmac_sha256

        secret = "test_secret_key"
        payload = b'{"event": "push"}'
        sig = hmac_lib.new(
            key=secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert verify_hmac_sha256(payload, sig, secret) is True

    def test_valid_with_prefix(self):
        import hashlib, hmac as hmac_lib
        from data_engine.ingestion.streams.webhook_receiver import verify_hmac_sha256

        secret = "my_secret"
        payload = b'{"action": "created"}'
        sig = "sha256=" + hmac_lib.new(
            key=secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert verify_hmac_sha256(payload, sig, secret) is True

    def test_invalid_signature(self):
        from data_engine.ingestion.streams.webhook_receiver import verify_hmac_sha256
        assert verify_hmac_sha256(b"payload", "wrongsig", "secret") is False

    def test_empty_signature(self):
        from data_engine.ingestion.streams.webhook_receiver import verify_hmac_sha256
        assert verify_hmac_sha256(b"payload", "", "secret") is False


# ─────────────────────────────────────────────────────────────────────────────
# WebhookReceiver
# ─────────────────────────────────────────────────────────────────────────────

class TestWebhookReceiver:
    @pytest.mark.asyncio
    async def test_receive_valid_json(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig(name="test", require_json=True)
        receiver = WebhookReceiver(config=cfg)
        body = json.dumps({"action": "push", "ref": "main"}).encode()
        result = await receiver.receive(body, headers={})
        assert result["status"] == "ok"
        assert "event_id" in result

    @pytest.mark.asyncio
    async def test_receive_invalid_json(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig(require_json=True)
        receiver = WebhookReceiver(config=cfg)
        result = await receiver.receive(b"not valid json{{", headers={})
        assert result["status"] == "error"
        assert "json_decode_error" in result["message"]

    @pytest.mark.asyncio
    async def test_receive_payload_too_large(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig(max_payload_bytes=10)
        receiver = WebhookReceiver(config=cfg)
        result = await receiver.receive(b"x" * 100, headers={})
        assert result["status"] == "error"
        assert result["message"] == "payload_too_large"

    @pytest.mark.asyncio
    async def test_receive_invalid_hmac(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig(secret="real_secret")
        receiver = WebhookReceiver(config=cfg)
        body = b'{"event": "push"}'
        result = await receiver.receive(
            body,
            headers={"X-Hub-Signature-256": "sha256=wrong_signature"},
        )
        assert result["status"] == "error"
        assert result["message"] == "invalid_signature"

    @pytest.mark.asyncio
    async def test_receive_valid_hmac(self):
        import hashlib, hmac as hmac_lib
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        secret = "test_secret"
        cfg = WebhookConfig(secret=secret)
        receiver = WebhookReceiver(config=cfg)
        body = b'{"action": "created"}'
        sig = "sha256=" + hmac_lib.new(
            key=secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        result = await receiver.receive(body, headers={"X-Hub-Signature-256": sig})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_allowed_events_filter(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig(allowed_events=["push", "pr"])
        receiver = WebhookReceiver(config=cfg)
        body = b'{"data": "ok"}'
        result = await receiver.receive(
            body,
            headers={"X-GitHub-Event": "issues"},
        )
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_metrics_increment(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig()
        receiver = WebhookReceiver(config=cfg)
        body = b'{"data": 1}'
        await receiver.receive(body, headers={})
        await receiver.receive(body, headers={})
        metrics = receiver.get_metrics()
        assert metrics.total_received == 2
        assert metrics.valid_payload == 2

    @pytest.mark.asyncio
    async def test_get_event_returns_none_on_timeout(self):
        from data_engine.ingestion.streams.webhook_receiver import (
            WebhookReceiver, WebhookConfig
        )
        cfg = WebhookConfig()
        receiver = WebhookReceiver(config=cfg)
        event = await receiver.get_event(timeout_s=0.05)
        assert event is None


# ─────────────────────────────────────────────────────────────────────────────
# Kafka
# ─────────────────────────────────────────────────────────────────────────────

class TestKafkaConsumerConfig:
    def test_defaults(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaConsumerConfig
        cfg = KafkaConsumerConfig()
        assert cfg.group_id == "hajeen-ingestion"
        assert cfg.auto_offset_reset == "earliest"
        assert cfg.deserializer == "json"

    def test_custom(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaConsumerConfig
        cfg = KafkaConsumerConfig(
            bootstrap_servers="kafka:9092",
            topics=["test.topic"],
            group_id="test-group",
            deserializer="string",
        )
        assert cfg.bootstrap_servers == "kafka:9092"
        assert "test.topic" in cfg.topics


class TestKafkaMetrics:
    def test_to_dict(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaMetrics
        m = KafkaMetrics(total_messages=50, valid_messages=48)
        d = m.to_dict()
        assert d["total_messages"] == 50
        assert d["valid_messages"] == 48

    def test_defaults(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaMetrics
        m = KafkaMetrics()
        assert m.is_connected is False
        assert m.dead_letter_size == 0


class TestKafkaStreamConsumerInit:
    def test_init_default_config(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaStreamConsumer
        consumer = KafkaStreamConsumer()
        assert not consumer._running
        assert consumer.config.group_id == "hajeen-ingestion"

    def test_get_metrics(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaStreamConsumer
        consumer = KafkaStreamConsumer()
        metrics = consumer.get_metrics()
        assert metrics.total_messages == 0

    def test_dead_letter_empty(self):
        from data_engine.ingestion.streams.kafka_consumer import KafkaStreamConsumer
        consumer = KafkaStreamConsumer()
        assert consumer.get_dead_letter_queue() == []
