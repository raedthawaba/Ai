"""Phase 8.4 — Conversation Memory: ذاكرة المحادثة."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm.base import LLMMessage


@dataclass
class Message:
    """رسالة في المحادثة."""
    role: str
    content: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_llm_message(self) -> LLMMessage:
        return LLMMessage(role=self.role, content=self.content)

    def to_dict(self) -> dict:
        return {
            "id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
        }


class ConversationMemory:
    """
    ذاكرة المحادثة لجلسة واحدة.

    المهام:
    - تخزين سجل الرسائل
    - الحصول على الرسائل للـ context
    - قص الذاكرة عند الحاجة
    - إحصائيات الاستخدام
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        max_messages: int = 50,
        max_tokens: int = 4000,
        tokens_per_word: float = 1.3,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.tokens_per_word = tokens_per_word
        self._messages: List[Message] = []
        self._system_prompt: Optional[str] = None
        self.created_at = time.time()
        self.updated_at = time.time()

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * self.tokens_per_word)

    def set_system_prompt(self, prompt: str) -> None:
        """تعيين system prompt."""
        self._system_prompt = prompt

    def add_user_message(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """إضافة رسالة مستخدم."""
        return self._add_message("user", content, metadata)

    def add_assistant_message(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """إضافة رسالة مساعد."""
        return self._add_message("assistant", content, metadata)

    def _add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        msg = Message(
            role=role,
            content=content,
            token_count=self._estimate_tokens(content),
            metadata=metadata or {},
        )
        self._messages.append(msg)
        self.updated_at = time.time()

        # قص الذاكرة إذا تجاوزت الحد
        if len(self._messages) > self.max_messages:
            self._trim_to_limit()

        return msg

    def _trim_to_limit(self) -> None:
        """قص الرسائل الأقدم مع الحفاظ على أول رسالة system."""
        excess = len(self._messages) - self.max_messages
        self._messages = self._messages[excess:]

    def get_messages(
        self,
        include_system: bool = True,
        max_tokens: Optional[int] = None,
    ) -> List[LLMMessage]:
        """الحصول على الرسائل كـ LLMMessages."""
        limit = max_tokens or self.max_tokens
        result: List[LLMMessage] = []

        if include_system and self._system_prompt:
            result.append(LLMMessage(role="system", content=self._system_prompt))

        # نضيف الرسائل من الأحدث للأقدم حتى الحد
        used_tokens = self._estimate_tokens(self._system_prompt or "")
        messages_to_add = []

        for msg in reversed(self._messages):
            msg_tokens = self._estimate_tokens(msg.content)
            if used_tokens + msg_tokens > limit and messages_to_add:
                break
            messages_to_add.insert(0, msg.to_llm_message())
            used_tokens += msg_tokens

        result.extend(messages_to_add)
        return result

    def get_last_n(self, n: int) -> List[Message]:
        """آخر n رسائل."""
        return self._messages[-n:]

    def clear(self) -> None:
        """مسح سجل المحادثة."""
        self._messages.clear()
        self.updated_at = time.time()

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def total_tokens(self) -> int:
        return sum(m.token_count for m in self._messages)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self._messages],
        }
