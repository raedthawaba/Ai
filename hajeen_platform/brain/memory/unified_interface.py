"""
UnifiedMemoryInterface — جسر الذاكرة الموحّد
=================================================
جميع أنظمة الذاكرة في المنصة تمر عبر هذه الواجهة.

المبدأ:
- MemoryFabric (brain/memory/) = مصدر الحقيقة الوحيد
- SessionManager (services/memory/) = واجهة توافقية (legacy bridge)
- ConversationMemory (services/memory/) = واجهة توافقية
- جميعهم يكتبون/يقرأون من نفس المصدر
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class UnifiedMemoryInterface:
    """واجهة الذاكرة الموحّدة — Singleton."""

    _instance: Optional["UnifiedMemoryInterface"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self) -> None:
        """تهيئة الواجهة الموحّدة."""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            try:
                from brain.memory.memory_fabric import get_memory_fabric
                self._fabric = get_memory_fabric()
                logger.info("UnifiedMemoryInterface: MemoryFabric connected ✓")
            except Exception as exc:
                logger.warning("UnifiedMemoryInterface: MemoryFabric unavailable — %s", exc)
                self._fabric = None
            self._initialized = True

    # ── Core Operations (write to MemoryFabric) ───────────────────────────

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """إضافة رسالة للذاكرة الموحّدة."""
        if self._fabric:
            try:
                self._fabric.add_message(session_id, role, content)
                logger.debug("Memory: added %s message to session %s", role, session_id)
            except Exception as exc:
                logger.warning("MemoryFabric write failed: %s", exc)

        # Bridge to SessionManager (legacy compatibility)
        try:
            from services.memory.session_manager import get_session_manager
            sm = get_session_manager()
            session = sm.get_or_create(session_id)
            session.add_message(role, content)
        except Exception as exc:
            logger.debug("SessionManager bridge skipped: %s", exc)

    async def get_context(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> List[Dict[str, str]]:
        """جلب سياق المحادثة."""
        if self._fabric:
            try:
                return self._fabric.get_window(session_id, max_messages)
            except Exception as exc:
                logger.warning("MemoryFabric read failed: %s", exc)

        # Fallback to SessionManager
        try:
            from services.memory.session_manager import get_session_manager
            sm = get_session_manager()
            session = sm.get_session(session_id)
            if session:
                return session.get_messages()[-max_messages:]
        except Exception as exc:
            logger.debug("SessionManager fallback failed: %s", exc)

        return []

    async def get_summary_context(self, session_id: str) -> str:
        """جلب ملخّص السياق."""
        if self._fabric:
            try:
                return self._fabric.get_summary_context(session_id)
            except Exception:
                pass
        return ""

    async def clear_session(self, session_id: str) -> None:
        """مسح جلسة."""
        if self._fabric:
            try:
                self._fabric.clear(session_id)
            except Exception:
                pass
        try:
            from services.memory.session_manager import get_session_manager
            sm = get_session_manager()
            sm.delete_session(session_id)
        except Exception:
            pass

    # ── Statistics ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الذاكرة."""
        stats = {"fabric_connected": self._fabric is not None}
        if self._fabric:
            try:
                stats["fabric_stats"] = self._fabric.get_stats()
            except Exception:
                pass
        return stats


# ── Singleton accessor ────────────────────────────────────────────────────

_unified_memory: Optional[UnifiedMemoryInterface] = None


def get_unified_memory() -> UnifiedMemoryInterface:
    """الحصول على واجهة الذاكرة الموحّدة."""
    global _unified_memory
    if _unified_memory is None:
        _unified_memory = UnifiedMemoryInterface()
    return _unified_memory
