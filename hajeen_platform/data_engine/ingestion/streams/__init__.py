"""Streams package — Phase 3 (Section 3.3).

يوفّر أنظمة استقبال البيانات المباشرة:
- WebSocket Listener
- Webhook Receiver
- Kafka Consumer
"""
from .websocket_listener import (
    WebSocketListener,
    WebSocketConfig,
    StreamMessage,
    StreamMetrics,
)
from .webhook_receiver import (
    WebhookReceiver,
    WebhookConfig,
    WebhookEvent,
    WebhookMetrics,
    verify_hmac_sha256,
)
from .kafka_consumer import (
    KafkaStreamConsumer,
    KafkaConsumerConfig,
    KafkaMessage,
    KafkaMetrics,
)

__all__ = [
    # WebSocket
    "WebSocketListener",
    "WebSocketConfig",
    "StreamMessage",
    "StreamMetrics",
    # Webhook
    "WebhookReceiver",
    "WebhookConfig",
    "WebhookEvent",
    "WebhookMetrics",
    "verify_hmac_sha256",
    # Kafka
    "KafkaStreamConsumer",
    "KafkaConsumerConfig",
    "KafkaMessage",
    "KafkaMetrics",
]
