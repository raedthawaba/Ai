"""
SessionManager (Adapter) — إدارة جلسات المحادثة
=============================================
تم تحويل هذا المكون إلى Compatibility Adapter.
لا يحتفظ بأي حالة (State) أو تخزين (Storage) مستقل.
جميع العمليات تمر عبر UnifiedMemoryInterface -> MemoryFabric.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hajeen_platform.brain.memory.unified_interface import get_unified_memory
from .conversation_memory import ConversationMemory


@dataclass
class ChatSession:
    """
    جلسة محادثة (Proxy Object).
    يعمل كواجهة للبيانات الموجودة في MemoryFabric.
    """
    session_id: str
    _unified_memory = get_unified_memory()
    
    @property
    def memory(self) -> ConversationMemory:
        """تحويل الذاكرة إلى Adapter أيضاً."""
        return ConversationMemory(session_id=self.session_id)

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """تمرير الكتابة للواجهة الموحدة."""
        import asyncio
        try:
            # نستخدم run_coroutine_threadsafe أو نقوم بتشغيلها كـ task إذا كنا في حلقة حدث
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._unified_memory.add_message(self.session_id, role, content, metadata))
            else:
                asyncio.run(self._unified_memory.add_message(self.session_id, role, content, metadata))
        except Exception:
            # Fallback لضمان عدم تعطل الكود القديم
            pass

    def add_turn(self, turn_result: Any) -> None:
        """متوافق مع ChatService القديم."""
        self.add_message("user", turn_result.user_message)
        self.add_message("assistant", turn_result.assistant_response, {
            "turn_id": turn_result.turn_id,
            "sources": turn_result.sources,
            "metrics": {
                "latency_ms": turn_result.latency_ms,
                "tokens": turn_result.tokens_used
            }
        })

    def to_dict(self) -> dict:
        """جلب البيانات من المصدر الموحد."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # ملاحظة: في بيئة الـ async الحقيقية، يجب أن تكون هذه الدالة async
                # لكن للحفاظ على التوافقية، سنحاول جلب البيانات بشكل متزامن إذا أمكن
                return {"session_id": self.session_id, "status": "adapter_active"}
            
            history = asyncio.run(self._unified_memory.get_context(self.session_id))
            return {
                "session_id": self.session_id,
                "message_count": len(history),
                "active": True,
                "adapter": True
            }
        except Exception:
            return {"session_id": self.session_id, "adapter": True}


class SessionManager:
    """
    إدارة الجلسات (Compatibility Adapter).
    لا يوجد تخزين محلي هنا؛ كل شيء في MemoryFabric.
    """

    def __init__(self, **kwargs):
        self._unified_memory = get_unified_memory()

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """استرجاع جلسة (Proxy)."""
        return ChatSession(session_id=session_id)

    def get_or_create(self, session_id: str, **kwargs) -> ChatSession:
        """استرجاع أو إنشاء جلسة (Proxy)."""
        return ChatSession(session_id=session_id)

    def create_session(self, session_id: Optional[str] = None, **kwargs) -> ChatSession:
        sid = session_id or str(uuid.uuid4())
        return ChatSession(session_id=sid)

    def delete_session(self, session_id: str) -> bool:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._unified_memory.clear_session(session_id))
            else:
                asyncio.run(self._unified_memory.clear_session(session_id))
            return True
        except Exception:
            return False

    def list_sessions(self, **kwargs) -> List[Dict[str, Any]]:
        """قائمة الجلسات من المصدر الموحد."""
        stats = self._unified_memory.get_stats()
        return [{"id": "all", "stats": stats}]


# Singleton
_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
