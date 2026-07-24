"""
UnifiedMemoryInterface — جسر الذاكرة الموحّد (V2)
=================================================
جميع أنظمة الذاكرة في المنصة تمر عبر هذه الواجهة.

المبدأ الصارم:
- MemoryFabric = مصدر الحقيقة الوحيد (SSOT)
- يمنع أي كتابة مباشرة للملفات أو قواعد البيانات من خارج MemoryFabric
- جميع المكونات القديمة أصبحت Compatibility Adapters
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
                from hajeen_platform.brain.memory.memory_fabric import get_memory_fabric
                self._fabric = get_memory_fabric()
                logger.info("UnifiedMemoryInterface: MemoryFabric connected (SSOT Mode) ✓")
            except Exception as exc:
                logger.warning("UnifiedMemoryInterface: MemoryFabric unavailable — %s", exc)
                self._fabric = None
            self._initialized = True

    def _ensure_fabric(self):
        if not hasattr(self, "_fabric") or self._fabric is None:
            from hajeen_platform.brain.memory.memory_fabric import get_memory_fabric
            self._fabric = get_memory_fabric()

    # ── Core Operations (Routed to MemoryFabric) ───────────────────────────

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """إضافة رسالة للذاكرة الموحّدة (المصدر الوحيد)."""
        self._ensure_fabric()
        if self._fabric:
            try:
                # الكتابة في MemoryFabric (التي تتولى التخزين الفعلي)
                conv = self._fabric.get_conversation(session_id)
                conv.add_message(role, content, metadata)
                logger.debug("Memory: added %s message to MemoryFabric for session %s", role, session_id)
            except Exception as exc:
                logger.error("CRITICAL: MemoryFabric write failed: %s", exc)

    async def get_context(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> List[Dict[str, str]]:
        """جلب سياق المحادثة من مصدر الحقيقة الوحيد."""
        self._ensure_fabric()
        if self._fabric:
            try:
                conv = self._fabric.get_conversation(session_id)
                return conv.get_window()[-max_messages:]
            except Exception as exc:
                logger.warning("MemoryFabric read failed: %s", exc)
        return []

    async def get_summary_context(self, session_id: str) -> str:
        """جلب ملخّص السياق من MemoryFabric."""
        self._ensure_fabric()
        if self._fabric:
            try:
                return self._fabric.get_conversation(session_id).get_summary_context()
            except Exception:
                pass
        return ""

    async def clear_session(self, session_id: str) -> None:
        """مسح جلسة من مصدر الحقيقة الوحيد."""
        self._ensure_fabric()
        if self._fabric:
            try:
                self._fabric.clear_session(session_id)
            except Exception:
                pass

    # ── Long-Term Memory (SSOT) ───────────────────────────────────────────

    async def remember(self, key: str, value: Any, metadata: Optional[Dict] = None) -> None:
        """حفظ معلومة في الذاكرة طويلة الأمد."""
        self._ensure_fabric()
        if self._fabric:
            self._fabric.remember(key, value, metadata)

    async def recall(self, key: str) -> Optional[Any]:
        """استرجاع معلومة من الذاكرة طويلة الأمد."""
        self._ensure_fabric()
        if self._fabric:
            return self._fabric.recall(key)
        return None

    # ── Statistics ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الذاكرة الموحدة."""
        self._ensure_fabric()
        stats = {"fabric_connected": self._fabric is not None}
        if self._fabric:
            try:
                stats["total_sessions"] = len(self._fabric._sessions)
                stats["total_conversations"] = len(self._fabric._conversations)
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
