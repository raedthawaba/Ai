"""Phase 8.4 — Session Manager: إدارة جلسات المحادثة."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .conversation_memory import ConversationMemory


@dataclass
class ChatSession:
    """جلسة محادثة كاملة."""
    session_id: str
    memory: ConversationMemory
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    active: bool = True

    def touch(self) -> None:
        """تحديث وقت آخر نشاط."""
        self.last_active = time.time()

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "message_count": self.memory.message_count,
            "total_tokens": self.memory.total_tokens,
            "active": self.active,
            "tags": self.tags,
        }


class SessionManager:
    """
    إدارة جلسات المحادثة مع persistence.

    المهام:
    - إنشاء وحذف الجلسات
    - تحميل وحفظ الجلسات
    - تنظيف الجلسات القديمة
    - استعلامات الجلسات
    """

    def __init__(
        self,
        session_ttl_seconds: float = 3600.0,
        max_sessions: int = 1000,
        cleanup_interval: int = 100,
    ):
        self._sessions: Dict[str, ChatSession] = {}
        self.session_ttl = session_ttl_seconds
        self.max_sessions = max_sessions
        self._cleanup_counter = 0
        self._cleanup_interval = cleanup_interval

    def create_session(
        self,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        max_messages: int = 50,
    ) -> ChatSession:
        """إنشاء جلسة جديدة."""
        sid = session_id or str(uuid.uuid4())

        if sid in self._sessions:
            return self._sessions[sid]

        memory = ConversationMemory(
            session_id=sid,
            max_messages=max_messages,
        )
        if system_prompt:
            memory.set_system_prompt(system_prompt)

        session = ChatSession(
            session_id=sid,
            memory=memory,
            metadata=metadata or {},
            tags=tags or [],
        )
        self._sessions[sid] = session

        self._cleanup_counter += 1
        if self._cleanup_counter >= self._cleanup_interval:
            self._cleanup_expired()

        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """استرجاع جلسة بالـ ID."""
        session = self._sessions.get(session_id)
        if session:
            if self._is_expired(session):
                self._sessions.pop(session_id, None)
                return None
            session.touch()
        return session

    def get_or_create(
        self,
        session_id: str,
        **kwargs,
    ) -> ChatSession:
        """استرجاع أو إنشاء جلسة."""
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id=session_id, **kwargs)
        return session

    def delete_session(self, session_id: str) -> bool:
        """حذف جلسة."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def _is_expired(self, session: ChatSession) -> bool:
        return session.idle_seconds > self.session_ttl

    def _cleanup_expired(self) -> int:
        """حذف الجلسات منتهية الصلاحية."""
        expired = [
            sid for sid, s in self._sessions.items()
            if self._is_expired(s)
        ]
        for sid in expired:
            del self._sessions[sid]
        self._cleanup_counter = 0
        return len(expired)

    def list_sessions(
        self,
        active_only: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """قائمة الجلسات."""
        sessions = list(self._sessions.values())
        if active_only:
            sessions = [s for s in sessions if not self._is_expired(s)]
        sessions.sort(key=lambda s: s.last_active, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": sum(
                1 for s in self._sessions.values()
                if not self._is_expired(s)
            ),
            "max_sessions": self.max_sessions,
            "session_ttl_seconds": self.session_ttl,
        }


# Singleton
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
