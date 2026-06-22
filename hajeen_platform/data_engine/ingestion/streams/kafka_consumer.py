"""Kafka Consumer — Phase 3 (Section 3.3).

نظام استهلاك حقيقي لـ Apache Kafka:
- Auto-reconnect مع exponential backoff
- Message deserialization (JSON + Avro stub)
- Dead-letter queue
- Graceful shutdown
- Consumer group management
- Offset management
- Stream metrics
- Async non-blocking

ملاحظة: يستخدم aiokafka إذا كان متاحاً، وإلا يعمل في simulation mode.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Optional aiokafka import
# ─────────────────────────────────────────────────────────────────────────────

try:
    from aiokafka import AIOKafkaConsumer
    from aiokafka.errors import KafkaError, KafkaConnectionError
    _KAFKA_AVAILABLE = True
    logger.info("kafka_consumer: aiokafka متاح")
except ImportError:
    _KAFKA_AVAILABLE = False
    logger.warning("kafka_consumer: aiokafka غير مثبّت — simulation mode")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KafkaConsumerConfig:
    """إعدادات Kafka Consumer."""

    bootstrap_servers: str = "localhost:9092"
    topics: List[str] = field(default_factory=lambda: ["hajeen.articles"])
    group_id: str = "hajeen-ingestion"
    auto_offset_reset: str = "earliest"         # "earliest" | "latest"
    enable_auto_commit: bool = True
    auto_commit_interval_ms: int = 5000
    max_poll_records: int = 500
    session_timeout_ms: int = 30_000
    heartbeat_interval_ms: int = 10_000
    reconnect_delay_s: float = 1.0
    max_reconnect_delay_s: float = 60.0
    max_reconnect_attempts: int = -1            # -1 = infinite
    buffer_size: int = 1000
    dead_letter_max: int = 200
    deserializer: str = "json"                  # "json" | "string" | "bytes"
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Kafka Message
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KafkaMessage:
    """رسالة Kafka واحدة."""

    topic: str
    partition: int
    offset: int
    key: Optional[str]
    value: Any
    timestamp: datetime
    valid: bool = True
    parse_error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "key": self.key,
            "timestamp": self.timestamp.isoformat(),
            "valid": self.valid,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Kafka Metrics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KafkaMetrics:
    """مقاييس Kafka Consumer."""

    total_messages: int = 0
    valid_messages: int = 0
    invalid_messages: int = 0
    total_reconnects: int = 0
    current_buffer_size: int = 0
    dead_letter_size: int = 0
    messages_by_topic: Dict[str, int] = field(default_factory=dict)
    is_connected: bool = False
    last_offset: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "total_messages": self.total_messages,
            "valid_messages": self.valid_messages,
            "invalid_messages": self.invalid_messages,
            "total_reconnects": self.total_reconnects,
            "buffer_size": self.current_buffer_size,
            "dead_letter_size": self.dead_letter_size,
            "is_connected": self.is_connected,
            "messages_by_topic": self.messages_by_topic,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Deserializer
# ─────────────────────────────────────────────────────────────────────────────

def _deserialize(raw: Optional[bytes], mode: str) -> Any:
    """فك تسلسل قيمة Kafka.

    Parameters
    ----------
    raw:
        bytes الخام من Kafka.
    mode:
        "json" | "string" | "bytes"

    Returns
    -------
    القيمة المحللة.
    """
    if raw is None:
        return None
    if mode == "bytes":
        return raw
    try:
        text = raw.decode("utf-8", errors="replace")
        if mode == "json":
            return json.loads(text)
        return text
    except Exception as exc:
        raise ValueError(f"Deserialization error ({mode}): {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# KafkaConsumer
# ─────────────────────────────────────────────────────────────────────────────

class KafkaStreamConsumer:
    """Kafka Consumer مستقر مع auto-reconnect وmessage validation.

    Parameters
    ----------
    config:
        KafkaConsumerConfig للتحكم في السلوك.
    message_handler:
        Callback غير متزامن للرسائل الصحيحة.
    """

    def __init__(
        self,
        config: Optional[KafkaConsumerConfig] = None,
        message_handler: Optional[Callable] = None,
    ) -> None:
        self.config = config or KafkaConsumerConfig()
        self.message_handler = message_handler
        self.metrics = KafkaMetrics()
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=self.config.buffer_size)
        self._dead_letter: List[KafkaMessage] = []
        self._running = False
        self._stop_event = asyncio.Event()
        self._consumer: Optional[object] = None

    # ─── Public API ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """بدء الاستهلاك في background."""
        if self._running:
            logger.warning("KafkaStreamConsumer: already running")
            return
        self._running = True
        self._stop_event.clear()
        asyncio.create_task(self._run_loop(), name=f"kafka_{self.config.group_id}")
        logger.info(
            "KafkaStreamConsumer: started topics=%s servers=%s",
            self.config.topics,
            self.config.bootstrap_servers,
        )

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        self._stop_event.set()
        if self._consumer and _KAFKA_AVAILABLE:
            try:
                await self._consumer.stop()
            except Exception as exc:
                logger.warning("KafkaStreamConsumer: stop error — %s", exc)
        logger.info("KafkaStreamConsumer: stopped")

    async def get_message(self, timeout_s: float = 5.0) -> Optional[KafkaMessage]:
        """انتظار رسالة من الـ buffer."""
        try:
            return await asyncio.wait_for(self._buffer.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def get_metrics(self) -> KafkaMetrics:
        self.metrics.current_buffer_size = self._buffer.qsize()
        return self.metrics

    def get_dead_letter_queue(self) -> List[KafkaMessage]:
        return list(self._dead_letter)

    # ─── Internal loop ───────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """حلقة الاتصال الرئيسية."""
        cfg = self.config
        reconnect_count = 0
        delay = cfg.reconnect_delay_s

        while self._running and not self._stop_event.is_set():
            try:
                if _KAFKA_AVAILABLE:
                    await self._consume_real()
                else:
                    await self._consume_simulation()
                reconnect_count = 0
                delay = cfg.reconnect_delay_s

            except Exception as exc:
                self.metrics.is_connected = False
                reconnect_count += 1
                self.metrics.total_reconnects += 1

                if (
                    cfg.max_reconnect_attempts >= 0
                    and reconnect_count > cfg.max_reconnect_attempts
                ):
                    logger.error(
                        "KafkaStreamConsumer: max_reconnects=%d reached",
                        cfg.max_reconnect_attempts,
                    )
                    break

                logger.warning(
                    "KafkaStreamConsumer: disconnected (#%d) — retry in %.1fs error=%s",
                    reconnect_count, delay, exc,
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=delay
                    )
                except asyncio.TimeoutError:
                    pass

                delay = min(delay * 2, cfg.max_reconnect_delay_s)

        self._running = False

    async def _consume_real(self) -> None:
        """استهلاك حقيقي من Kafka عبر aiokafka."""
        cfg = self.config
        self._consumer = AIOKafkaConsumer(
            *cfg.topics,
            bootstrap_servers=cfg.bootstrap_servers,
            group_id=cfg.group_id,
            auto_offset_reset=cfg.auto_offset_reset,
            enable_auto_commit=cfg.enable_auto_commit,
            auto_commit_interval_ms=cfg.auto_commit_interval_ms,
            session_timeout_ms=cfg.session_timeout_ms,
            heartbeat_interval_ms=cfg.heartbeat_interval_ms,
            max_poll_records=cfg.max_poll_records,
        )

        await self._consumer.start()
        self.metrics.is_connected = True
        logger.info("KafkaStreamConsumer: connected to %s", cfg.bootstrap_servers)

        try:
            async for record in self._consumer:
                if self._stop_event.is_set():
                    break

                await self._process_record(
                    topic=record.topic,
                    partition=record.partition,
                    offset=record.offset,
                    key=record.key,
                    value=record.value,
                    timestamp_ms=record.timestamp,
                )
        finally:
            await self._consumer.stop()
            self.metrics.is_connected = False

    async def _consume_simulation(self) -> None:
        """Simulation mode عندما aiokafka غير متاح."""
        logger.info("KafkaStreamConsumer: simulation mode (aiokafka not installed)")
        self.metrics.is_connected = True
        # في simulation نبقى في انتظار حتى stop
        await self._stop_event.wait()
        self.metrics.is_connected = False

    async def _process_record(
        self,
        topic: str,
        partition: int,
        offset: int,
        key: Optional[bytes],
        value: Optional[bytes],
        timestamp_ms: int,
    ) -> None:
        """معالجة record Kafka واحد."""
        cfg = self.config
        self.metrics.total_messages += 1
        self.metrics.messages_by_topic[topic] = (
            self.metrics.messages_by_topic.get(topic, 0) + 1
        )
        self.metrics.last_offset[f"{topic}:{partition}"] = offset

        # Deserialization
        valid = True
        parse_error = None
        try:
            deserialized_value = _deserialize(value, cfg.deserializer)
            deserialized_key = key.decode("utf-8", errors="replace") if key else None
        except Exception as exc:
            valid = False
            parse_error = str(exc)
            deserialized_value = None
            deserialized_key = None

        ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        msg = KafkaMessage(
            topic=topic,
            partition=partition,
            offset=offset,
            key=deserialized_key,
            value=deserialized_value,
            timestamp=ts,
            valid=valid,
            parse_error=parse_error,
        )

        if valid:
            self.metrics.valid_messages += 1

            if self.message_handler:
                try:
                    await self.message_handler(msg)
                except Exception as exc:
                    logger.error("KafkaStreamConsumer: handler error — %s", exc)
                    self._add_to_dead_letter(msg)

            try:
                self._buffer.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning("KafkaStreamConsumer: buffer full — dropping message")
                self._add_to_dead_letter(msg)
        else:
            self.metrics.invalid_messages += 1
            logger.debug(
                "KafkaStreamConsumer: invalid message topic=%s offset=%d error=%s",
                topic, offset, parse_error,
            )
            self._add_to_dead_letter(msg)

    def _add_to_dead_letter(self, msg: KafkaMessage) -> None:
        cfg = self.config
        if len(self._dead_letter) < cfg.dead_letter_max:
            self._dead_letter.append(msg)
            self.metrics.dead_letter_size = len(self._dead_letter)
