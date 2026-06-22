"""Phase 8.6 — Chat Session: إدارة جلسة دردشة واحدة."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm.base import LLMMessage
from services.memory.conversation_memory import ConversationMemory


@dataclass
class TurnResult:
    """نتيجة دورة محادثة واحدة."""
    turn_id: str
    user_message: str
    assistant_response: str
    sources: List[Dict[str, Any]]
    latency_ms: float
    tokens_used: int
    model: str
    provider: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "user_message": self.user_message[:200],
            "assistant_response": self.assistant_response,
            "sources_count": len(self.sources),
            "latency_ms": round(self.latency_ms, 2),
            "tokens_used": self.tokens_used,
            "model": self.model,
            "timestamp": self.timestamp,
        }


class ChatSession:
    """
    جلسة دردشة كاملة — وحدة التفاعل الأساسية.

    تُدير:
    - الذاكرة والسياق
    - تاريخ الأدوار
    - إحصائيات الجلسة
    - دعم RAG في الجلسة
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_history: int = 20,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.memory = ConversationMemory(
            session_id=self.session_id,
            max_messages=max_history,
        )
        if system_prompt:
            self.memory.set_system_prompt(system_prompt)

        self._turns: List[TurnResult] = []
        self.created_at = time.time()
        self.last_active = time.time()
        self._metadata: Dict[str, Any] = {}

    def add_turn(self, result: TurnResult) -> None:
        """إضافة دورة محادثة للسجل."""
        self._turns.append(result)
        self.memory.add_user_message(result.user_message)
        self.memory.add_assistant_message(result.assistant_response)
        self.last_active = time.time()

    def get_context_messages(
        self,
        max_tokens: Optional[int] = None,
    ) -> List[LLMMessage]:
        """الحصول على رسائل السياق للإرسال للـ LLM."""
        return self.memory.get_messages(
            include_system=True,
            max_tokens=max_tokens,
        )

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def total_tokens_used(self) -> int:
        return sum(t.tokens_used for t in self._turns)

    @property
    def avg_latency_ms(self) -> float:
        if not self._turns:
            return 0.0
        return sum(t.latency_ms for t in self._turns) / len(self._turns)

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active

    def get_history(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._turns]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "total_tokens": self.total_tokens_used,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "created_at": self.created_at,
            "last_active": self.last_active,
        }
