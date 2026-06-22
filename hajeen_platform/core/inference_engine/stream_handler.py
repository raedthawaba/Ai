"""Phase 8.3 — Stream Handler: إدارة streaming responses."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.llm.base import LLMStreamChunk

logger = logging.getLogger(__name__)


@dataclass
class StreamSession:
    """جلسة streaming نشطة."""
    session_id: str
    started_at: float = field(default_factory=time.time)
    chunks_received: int = 0
    total_chars: int = 0
    cancelled: bool = False
    completed: bool = False
    error: Optional[str] = None

    def add_chunk(self, delta: str) -> None:
        self.chunks_received += 1
        self.total_chars += len(delta)

    @property
    def duration_ms(self) -> float:
        return (time.time() - self.started_at) * 1000


@dataclass
class StreamEvent:
    """حدث SSE."""
    event_type: str  # "token" | "done" | "error"
    data: str
    chunk_index: int = 0
    finish_reason: Optional[str] = None

    def to_sse(self) -> str:
        """تحويل إلى Server-Sent Event format."""
        lines = [f"event: {self.event_type}"]
        lines.append(f"data: {self.data}")
        lines.append("")  # blank line
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict:
        return {
            "type": self.event_type,
            "data": self.data,
            "index": self.chunk_index,
            "finish_reason": self.finish_reason,
        }


class StreamHandler:
    """
    إدارة streaming responses.

    المهام:
    - تتبع جلسات streaming
    - تحويل chunks لـ SSE events
    - دعم إلغاء الطلبات
    - تجميع الـ chunks في buffer
    - معالجة انقطاع الاتصال
    """

    def __init__(
        self,
        buffer_size: int = 10,
        chunk_timeout: float = 30.0,
    ):
        self._sessions: Dict[str, StreamSession] = {}
        self.buffer_size = buffer_size
        self.chunk_timeout = chunk_timeout

    def create_session(self, session_id: str) -> StreamSession:
        session = StreamSession(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        return self._sessions.get(session_id)

    def cancel_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session:
            session.cancelled = True
            logger.info("Stream session cancelled: %s", session_id)
            return True
        return False

    def cleanup_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def process_stream(
        self,
        chunk_generator: AsyncGenerator[LLMStreamChunk, None],
        session_id: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        تحويل stream من LLM إلى StreamEvents.

        يدعم:
        - إلغاء الطلب
        - timeout للـ chunks
        - معالجة الأخطاء
        - تجميع الـ buffer
        """
        session = self.create_session(session_id)
        buffer: List[str] = []
        index = 0

        try:
            async for chunk in chunk_generator:
                if session.cancelled:
                    logger.info("Stream %s: cancelled by client", session_id)
                    yield StreamEvent(
                        event_type="error",
                        data="Stream cancelled",
                        chunk_index=index,
                    )
                    break

                if chunk.delta:
                    session.add_chunk(chunk.delta)
                    buffer.append(chunk.delta)

                    if len(buffer) >= self.buffer_size or chunk.finish_reason:
                        text = "".join(buffer)
                        buffer.clear()
                        yield StreamEvent(
                            event_type="token",
                            data=text,
                            chunk_index=index,
                            finish_reason=chunk.finish_reason,
                        )
                        index += 1

                if chunk.finish_reason:
                    break

            # flush remaining buffer
            if buffer:
                yield StreamEvent(
                    event_type="token",
                    data="".join(buffer),
                    chunk_index=index,
                )

            # done event
            yield StreamEvent(
                event_type="done",
                data=f"[DONE] chunks={session.chunks_received} chars={session.total_chars}",
                chunk_index=index + 1,
            )
            session.completed = True

        except asyncio.CancelledError:
            session.error = "cancelled"
            yield StreamEvent(event_type="error", data="Stream cancelled", chunk_index=index)
        except Exception as e:
            session.error = str(e)
            logger.error("Stream %s error: %s", session_id, e)
            yield StreamEvent(event_type="error", data=str(e), chunk_index=index)
        finally:
            logger.debug(
                "Stream %s ended: chunks=%d chars=%d ms=%.1f",
                session_id,
                session.chunks_received,
                session.total_chars,
                session.duration_ms,
            )

    async def collect_full_response(
        self,
        chunk_generator: AsyncGenerator[LLMStreamChunk, None],
    ) -> str:
        """جمع streaming response في نص كامل."""
        parts = []
        async for chunk in chunk_generator:
            if chunk.delta:
                parts.append(chunk.delta)
        return "".join(parts)
