"""
MemoryManager (Adapter) — إدارة الذاكرة المركزية (Legacy)
=========================================================
تم تحويل هذا المكون إلى Compatibility Adapter.
تم إلغاء الكتابة المباشرة لـ storage_data/conversations.
جميع العمليات تمر عبر UnifiedMemoryInterface -> MemoryFabric.
"""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict, List, Optional
from hajeen_platform.brain.memory.unified_interface import get_unified_memory

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    واجهة الذاكرة (Compatibility Adapter).
    تم حذف المكونات التي تكتب مباشرة للملفات (ShortTermMemory, LongTermMemory, ConversationStore).
    """

    def __init__(self, **kwargs) -> None:
        self._unified_memory = get_unified_memory()
        logger.info("MemoryManager initialized as Adapter (SSOT Mode)")

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        persist: bool = True,
        metadata: Optional[Dict] = None,
    ) -> None:
        """توجيه الكتابة للواجهة الموحدة ومنع الكتابة المباشرة للملفات."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._unified_memory.add_message(session_id, role, content, metadata))
            else:
                asyncio.run(self._unified_memory.add_message(session_id, role, content, metadata))
        except Exception as e:
            logger.error("MemoryManager Adapter write failed: %s", e)

    def get_recent_messages(
        self, session_id: str, last_n: int = 20
    ) -> List[Dict]:
        """جلب الرسائل من المصدر الموحد."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return []
            return asyncio.run(self._unified_memory.get_context(session_id, last_n))
        except Exception:
            return []

    def get_full_history(self, session_id: str) -> List[Dict]:
        """جلب التاريخ الكامل من المصدر الموحد."""
        return self.get_recent_messages(session_id, last_n=1000)

    def remember(self, session_id: str, key: str, value: Any) -> None:
        """توجيه للذاكرة طويلة الأمد في MemoryFabric."""
        try:
            loop = asyncio.get_event_loop()
            full_key = f"{session_id}:{key}"
            if loop.is_running():
                loop.create_task(self._unified_memory.remember(full_key, value))
            else:
                asyncio.run(self._unified_memory.remember(full_key, value))
        except Exception:
            pass

    def recall(self, session_id: str, key: str, default: Any = None) -> Any:
        """استرجاع من الذاكرة طويلة الأمد في MemoryFabric."""
        try:
            full_key = f"{session_id}:{key}"
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return default
            val = asyncio.run(self._unified_memory.recall(full_key))
            return val if val is not None else default
        except Exception:
            return default

    def forget(self, session_id: str, key: str) -> bool:
        # MemoryFabric حالياً لا يدعم الحذف الصريح في الواجهة البسيطة
        return True

    def clear_session(self, session_id: str) -> None:
        """مسح الجلسة من المصدر الموحد."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._unified_memory.clear_session(session_id))
            else:
                asyncio.run(self._unified_memory.clear_session(session_id))
        except Exception:
            pass

    def session_stats(self, session_id: str) -> Dict:
        return {
            "session_id": session_id,
            "adapter": True,
            "ssot": "MemoryFabric"
        }
