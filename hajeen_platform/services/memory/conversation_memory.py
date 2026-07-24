"""
ConversationMemory (Adapter) — ذاكرة المحادثة
=============================================
تم تحويل هذا المكون إلى Compatibility Adapter.
لا يحتفظ بأي حالة مستقلة؛ يمرر العمليات إلى UnifiedMemoryInterface.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from hajeen_platform.brain.memory.unified_interface import get_unified_memory

class ConversationMemory:
    """
    ذاكرة المحادثة (Adapter).
    """

    def __init__(self, session_id: str, **kwargs):
        self.session_id = session_id
        self._unified_memory = get_unified_memory()

    def add_user_message(self, content: str, metadata: Optional[Dict] = None) -> None:
        self._add_sync("user", content, metadata)

    def add_assistant_message(self, content: str, metadata: Optional[Dict] = None) -> None:
        self._add_sync("assistant", content, metadata)

    def _add_sync(self, role: str, content: str, metadata: Optional[Dict] = None):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._unified_memory.add_message(self.session_id, role, content, metadata))
            else:
                asyncio.run(self._unified_memory.add_message(self.session_id, role, content, metadata))
        except Exception:
            pass

    def get_messages(self, **kwargs) -> List[Any]:
        """جلب الرسائل من المصدر الموحد."""
        try:
            # ملاحظة: هذه الدالة كانت تزود كائنات LLMMessage، سنحاول محاكاتها
            from core.llm.base import LLMMessage
            
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # في بيئة async، يفضل استخدام await، لكن للتوافق سنعيد قائمة فارغة إذا تعذر الجلب المتزامن
                return []
            
            history = asyncio.run(self._unified_memory.get_context(self.session_id))
            return [LLMMessage(role=m["role"], content=m["content"]) for m in history]
        except Exception:
            return []

    def clear(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._unified_memory.clear_session(self.session_id))
            else:
                asyncio.run(self._unified_memory.clear_session(self.session_id))
        except Exception:
            pass

    @property
    def message_count(self) -> int:
        return 0 # Placeholder

    @property
    def total_tokens(self) -> int:
        return 0 # Placeholder
