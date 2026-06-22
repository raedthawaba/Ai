"""WebSocket Listener — Phase 3 (Section 3.3).

نظام استقبال حقيقي للبيانات من WebSocket endpoints:
- Auto-reconnect مع exponential backoff
- Heartbeat monitoring
- Message validation
- Buffer مع max_size
- Dead-letter queue للرسائل التالفة
- Graceful shutdown
- Stream metrics
- Async non-blocking
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
# Optional websockets import
# ─────────────────────────────────────────────────────────────────────────────

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    logger.warning("websocket_listener: مكتبة websockets غير مثبّتة")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WebSocketConfig:
    """إعدادات WebSocket Listener."""

    url: str                                  # WebSocket URL
    name: str = "ws_listener"                # اسم للـ logging
    reconnect_delay_s: float = 1.0           # تأخير أول reconnect
    max_reconnect_delay_s: float = 60.0      # حد أقصى للتأخير
    max_reconnect_attempts: int = -1          # -1 = infinite
    heartbeat_interval_s: float = 30.0       # فترة heartbeat
    heartbeat_timeout_s: float = 10.0        # timeout انتظار pong
    message_timeout_s: float = 60.0          # timeout لرسالة جديدة
    buffer_size: int = 1000                   # حجم buffer
    dead_letter_max: int = 100               # حجم Dead Letter Queue
    extra_headers: Dict[str, str] = field(default_factory=dict)
    ping_message: Optional[str] = None       # رسالة ping مخصصة (None = websocket ping)
    connection_timeout_s: float = 15.0       # timeout الاتصال


# ─────────────────────────────────────────────────────────────────────────────
# Stream Message
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StreamMessage:
    """رسالة stream واحدة."""

    raw: str
    data: Any = None
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    valid: bool = True
    parse_error: Optional[str] = None

    def is_json(self) -> bool:
        return self.data is not None and isinstance(self.data, (dict, list))


# ─────────────────────────────────────────────────────────────────────────────
# Stream Metrics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StreamMetrics:
    """مقاييس WebSocket stream."""

    total_messages: int = 0
    valid_messages: int = 0
    invalid_messages: int = 0
    total_reconnects: int = 0
    current_buffer_size: int = 0
    dead_letter_size: int = 0
    total_uptime_s: float = 0.0
    last_message_at: Optional[datetime] = None
    is_connected: bool = False

    def to_dict(self) -> Dict:
        return {
            "total_messages": self.total_messages,
            "valid_messages": self.valid_messages,
            "invalid_messages": self.invalid_messages,
            "total_reconnects": self.total_reconnects,
            "buffer_size": self.current_buffer_size,
            "dead_letter_size": self.dead_letter_size,
            "uptime_s": round(self.total_uptime_s, 1),
            "is_connected": self.is_connected,
        }


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Listener
# ─────────────────────────────────────────────────────────────────────────────

class WebSocketListener:
    """Listener حقيقي لـ WebSocket مع auto-reconnect وheartbeat monitoring.

    Parameters
    ----------
    config:
        WebSocketConfig للتحكم في السلوك.
    message_handler:
        Callback غير متزامن يُستدعى لكل رسالة صحيحة.
        Signature: async def handler(msg: StreamMessage) -> None
    """

    def __init__(
        self,
        config: WebSocketConfig,
        message_handler: Optional[Callable] = None,
    ) -> None:
        self.config = config
        self.message_handler = message_handler
        self.metrics = StreamMetrics()
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=config.buffer_size)
        self._dead_letter: List[StreamMessage] = []
        self._running = False
        self._connected = False
        self._start_time: Optional[float] = None
        self._stop_event = asyncio.Event()

    # ─── Public API ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """بدء الاستماع (non-blocking — يعمل في background)."""
        if self._running:
            logger.warning("[%s] WebSocketListener: already running", self.config.name)
            return
        self._running = True
        self._stop_event.clear()
        self._start_time = time.monotonic()
        asyncio.create_task(self._run_loop(), name=f"ws_{self.config.name}")
        logger.info("[%s] WebSocketListener: started url=%s", self.config.name, self.config.url)

    async def stop(self) -> None:
        """إيقاف graceful."""
        self._running = False
        self._stop_event.set()
        logger.info("[%s] WebSocketListener: stopping", self.config.name)

    async def get_message(self, timeout_s: float = 5.0) -> Optional[StreamMessage]:
        """انتظار رسالة من الـ buffer.

        Parameters
        ----------
        timeout_s:
            مهلة الانتظار.

        Returns
        -------
        StreamMessage أو None عند timeout.
        """
        try:
            return await asyncio.wait_for(self._buffer.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def get_dead_letter_queue(self) -> List[StreamMessage]:
        """إرجاع الرسائل التالفة."""
        return list(self._dead_letter)

    def clear_dead_letter_queue(self) -> None:
        """مسح Dead Letter Queue."""
        self._dead_letter.clear()
        self.metrics.dead_letter_size = 0

    def get_metrics(self) -> StreamMetrics:
        """إرجاع مقاييس الـ stream."""
        if self._start_time:
            self.metrics.total_uptime_s = time.monotonic() - self._start_time
        self.metrics.current_buffer_size = self._buffer.qsize()
        return self.metrics

    # ─── Internal loop ───────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """حلقة الاتصال الرئيسية مع exponential backoff."""
        cfg = self.config
        reconnect_count = 0
        delay = cfg.reconnect_delay_s

        while self._running and not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
                reconnect_count = 0
                delay = cfg.reconnect_delay_s  # reset بعد نجاح

            except Exception as exc:
                self._connected = False
                self.metrics.is_connected = False
                reconnect_count += 1
                self.metrics.total_reconnects += 1

                if (
                    cfg.max_reconnect_attempts >= 0
                    and reconnect_count > cfg.max_reconnect_attempts
                ):
                    logger.error(
                        "[%s] WebSocketListener: max_reconnects=%d reached — stopping",
                        cfg.name, cfg.max_reconnect_attempts,
                    )
                    break

                logger.warning(
                    "[%s] WebSocketListener: disconnected (#%d) — retry in %.1fs error=%s",
                    cfg.name, reconnect_count, delay, exc,
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=delay
                    )
                except asyncio.TimeoutError:
                    pass

                # Exponential backoff
                delay = min(delay * 2, cfg.max_reconnect_delay_s)

        self._running = False
        logger.info("[%s] WebSocketListener: stopped", cfg.name)

    async def _connect_and_listen(self) -> None:
        """الاتصال بـ WebSocket والاستماع للرسائل."""
        if not _WS_AVAILABLE:
            logger.warning("[%s] WebSocketListener: websockets not installed", self.config.name)
            await asyncio.sleep(5)
            return

        cfg = self.config
        try:
            async with websockets.connect(
                cfg.url,
                extra_headers=cfg.extra_headers,
                open_timeout=cfg.connection_timeout_s,
                ping_interval=cfg.heartbeat_interval_s,
                ping_timeout=cfg.heartbeat_timeout_s,
            ) as ws:
                self._connected = True
                self.metrics.is_connected = True
                logger.info("[%s] WebSocketListener: connected url=%s", cfg.name, cfg.url)

                async for raw_message in ws:
                    if self._stop_event.is_set():
                        break
                    await self._process_message(str(raw_message))

        except Exception as exc:
            self._connected = False
            self.metrics.is_connected = False
            raise

    async def _process_message(self, raw: str) -> None:
        """معالجة رسالة واحدة."""
        cfg = self.config
        self.metrics.total_messages += 1
        self.metrics.last_message_at = datetime.now(timezone.utc)

        # محاولة parse JSON
        data = None
        parse_error = None
        try:
            data = json.loads(raw)
            valid = True
        except json.JSONDecodeError as exc:
            valid = False
            parse_error = str(exc)

        msg = StreamMessage(
            raw=raw,
            data=data,
            source=cfg.name,
            valid=valid,
            parse_error=parse_error,
        )

        if valid:
            self.metrics.valid_messages += 1

            # إرسال للـ handler
            if self.message_handler:
                try:
                    await self.message_handler(msg)
                except Exception as exc:
                    logger.error("[%s] message_handler error: %s", cfg.name, exc)

            # إضافة للـ buffer (non-blocking)
            try:
                self._buffer.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning("[%s] buffer full — dropping oldest message", cfg.name)
                try:
                    self._buffer.get_nowait()
                    self._buffer.put_nowait(msg)
                except Exception:
                    pass
        else:
            self.metrics.invalid_messages += 1
            logger.debug(
                "[%s] invalid message (parse_error=%s): %.100s",
                cfg.name, parse_error, raw,
            )
            # إضافة للـ Dead Letter Queue
            if len(self._dead_letter) < cfg.dead_letter_max:
                self._dead_letter.append(msg)
                self.metrics.dead_letter_size = len(self._dead_letter)
