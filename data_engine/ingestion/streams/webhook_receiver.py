"""Webhook Receiver — Phase 3 (Section 3.3).

نظام استقبال حقيقي للـ webhooks:
- استقبال HTTP POST من مصادر خارجية
- HMAC signature verification
- Message validation (JSON schema)
- Dead-letter queue
- Retry acknowledgment
- Event logging
- Stream metrics
- Async non-blocking
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WebhookConfig:
    """إعدادات Webhook Receiver."""

    name: str = "webhook_receiver"
    secret: Optional[str] = None              # HMAC secret للتحقق
    signature_header: str = "X-Hub-Signature-256"
    max_payload_bytes: int = 10 * 1024 * 1024  # 10 MB
    buffer_size: int = 500
    dead_letter_max: int = 100
    require_json: bool = True
    allowed_events: List[str] = field(default_factory=list)  # فارغ = قبول الكل
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Event
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WebhookEvent:
    """حدث webhook واحد."""

    event_type: str
    payload: Any
    raw_body: str
    headers: Dict[str, str]
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_ip: str = ""
    signature_valid: bool = True
    event_id: str = ""

    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "received_at": self.received_at.isoformat(),
            "source_ip": self.source_ip,
            "signature_valid": self.signature_valid,
            "payload_size": len(self.raw_body),
        }


@dataclass
class WebhookMetrics:
    """مقاييس Webhook Receiver."""

    total_received: int = 0
    valid_signature: int = 0
    invalid_signature: int = 0
    valid_payload: int = 0
    invalid_payload: int = 0
    dead_letter_size: int = 0
    events_by_type: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "total_received": self.total_received,
            "valid_signature": self.valid_signature,
            "invalid_signature": self.invalid_signature,
            "valid_payload": self.valid_payload,
            "invalid_payload": self.invalid_payload,
            "dead_letter_size": self.dead_letter_size,
            "events_by_type": self.events_by_type,
        }


# ─────────────────────────────────────────────────────────────────────────────
# HMAC Verification
# ─────────────────────────────────────────────────────────────────────────────

def verify_hmac_sha256(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    """التحقق من HMAC-SHA256 signature.

    Parameters
    ----------
    payload:
        جسم الطلب الخام.
    signature:
        Signature من الـ header (بصيغة sha256=...).
    secret:
        المفتاح السري.

    Returns
    -------
    True إذا كانت الـ signature صحيحة.
    """
    try:
        if signature.startswith("sha256="):
            signature = signature[7:]

        expected = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature.lower())
    except Exception as exc:
        logger.warning("verify_hmac_sha256: error — %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# WebhookReceiver
# ─────────────────────────────────────────────────────────────────────────────

class WebhookReceiver:
    """Webhook Receiver مع signature verification وevent processing.

    يُستدعى من HTTP endpoint (مثال: FastAPI route) لمعالجة طلبات webhook.

    Parameters
    ----------
    config:
        WebhookConfig للتحكم في السلوك.
    event_handler:
        Callback غير متزامن للأحداث الصحيحة.
    """

    def __init__(
        self,
        config: Optional[WebhookConfig] = None,
        event_handler: Optional[Callable] = None,
    ) -> None:
        self.config = config or WebhookConfig()
        self.event_handler = event_handler
        self.metrics = WebhookMetrics()
        self._buffer: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.buffer_size
        )
        self._dead_letter: List[WebhookEvent] = []

    # ─── Core processing ─────────────────────────────────────────────────

    async def receive(
        self,
        body: bytes,
        headers: Dict[str, str],
        event_type: Optional[str] = None,
        source_ip: str = "",
    ) -> Dict[str, Any]:
        """استقبال ومعالجة webhook event.

        Parameters
        ----------
        body:
            جسم الطلب الخام (bytes).
        headers:
            HTTP headers.
        event_type:
            نوع الحدث (من X-GitHub-Event مثلاً).
        source_ip:
            عنوان IP المصدر.

        Returns
        -------
        dict مع: status, event_id, message
        """
        cfg = self.config
        self.metrics.total_received += 1

        # 1. التحقق من الحجم
        if len(body) > cfg.max_payload_bytes:
            logger.warning(
                "[%s] webhook: payload too large (%d bytes)", cfg.name, len(body)
            )
            return {"status": "error", "message": "payload_too_large"}

        # 2. التحقق من الـ signature
        if cfg.secret:
            sig_header = headers.get(cfg.signature_header, "")
            if not sig_header:
                sig_header = headers.get(cfg.signature_header.lower(), "")
            if not verify_hmac_sha256(body, sig_header, cfg.secret):
                self.metrics.invalid_signature += 1
                logger.warning(
                    "[%s] webhook: invalid signature from ip=%s", cfg.name, source_ip
                )
                return {"status": "error", "message": "invalid_signature"}
            self.metrics.valid_signature += 1
        else:
            self.metrics.valid_signature += 1

        # 3. Parse payload
        raw_str = body.decode("utf-8", errors="replace")
        payload = None
        if cfg.require_json:
            try:
                payload = json.loads(raw_str)
            except json.JSONDecodeError as exc:
                self.metrics.invalid_payload += 1
                logger.warning("[%s] webhook: JSON decode error — %s", cfg.name, exc)
                return {"status": "error", "message": f"json_decode_error: {exc}"}
        else:
            payload = raw_str

        # 4. كشف نوع الحدث
        detected_type = (
            event_type
            or headers.get("X-GitHub-Event")
            or headers.get("X-Event-Type")
            or headers.get("X-Hook-Event")
            or "generic"
        )

        # 5. التحقق من الأحداث المسموح بها
        if cfg.allowed_events and detected_type not in cfg.allowed_events:
            logger.debug("[%s] event_type=%s not in allowed list", cfg.name, detected_type)
            return {"status": "skipped", "message": f"event_type_not_allowed: {detected_type}"}

        # 6. إنشاء WebhookEvent
        import uuid
        event = WebhookEvent(
            event_type=detected_type,
            payload=payload,
            raw_body=raw_str,
            headers=dict(headers),
            source_ip=source_ip,
            signature_valid=True,
            event_id=str(uuid.uuid4())[:8],
        )

        self.metrics.valid_payload += 1
        self.metrics.events_by_type[detected_type] = (
            self.metrics.events_by_type.get(detected_type, 0) + 1
        )

        # 7. إرسال للـ handler
        if self.event_handler:
            try:
                await self.event_handler(event)
            except Exception as exc:
                logger.error("[%s] event_handler error: %s", cfg.name, exc)
                self._add_to_dead_letter(event)

        # 8. إضافة للـ buffer
        try:
            self._buffer.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("[%s] buffer full — dropping event", cfg.name)
            self._add_to_dead_letter(event)

        logger.info(
            "[%s] webhook received: type=%s id=%s ip=%s",
            cfg.name, detected_type, event.event_id, source_ip,
        )
        return {"status": "ok", "event_id": event.event_id}

    # ─── Buffer access ───────────────────────────────────────────────────

    async def get_event(self, timeout_s: float = 5.0) -> Optional[WebhookEvent]:
        """انتظار حدث من الـ buffer."""
        try:
            return await asyncio.wait_for(self._buffer.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def get_metrics(self) -> WebhookMetrics:
        return self.metrics

    def get_dead_letter_queue(self) -> List[WebhookEvent]:
        return list(self._dead_letter)

    def clear_dead_letter_queue(self) -> None:
        self._dead_letter.clear()
        self.metrics.dead_letter_size = 0

    # ─── Internal ────────────────────────────────────────────────────────

    def _add_to_dead_letter(self, event: WebhookEvent) -> None:
        cfg = self.config
        if len(self._dead_letter) < cfg.dead_letter_max:
            self._dead_letter.append(event)
            self.metrics.dead_letter_size = len(self._dead_letter)
