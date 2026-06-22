from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager


class MemoryService:
    """Service facade over the MemoryManager for API consumption."""

    def __init__(self, manager: Optional[MemoryManager] = None) -> None:
        self._manager = manager or get_memory_manager()

    def add_user_message(self, session_id: str, content: str) -> None:
        self._manager.add_message(session_id, "user", content)

    def add_assistant_message(self, session_id: str, content: str) -> None:
        self._manager.add_message(session_id, "assistant", content)

    def get_context(self, session_id: str, last_n: int = 20) -> List[Dict]:
        return self._manager.get_recent_messages(session_id, last_n)

    def get_full_history(self, session_id: str) -> List[Dict]:
        return self._manager.get_full_history(session_id)

    def remember(self, session_id: str, key: str, value: Any) -> None:
        self._manager.remember(session_id, key, value)

    def recall(self, session_id: str, key: str, default: Any = None) -> Any:
        return self._manager.recall(session_id, key, default)

    def clear(self, session_id: str) -> None:
        self._manager.clear_session(session_id)
        logger.info("Memory cleared for session: %s", session_id)

    def stats(self, session_id: str) -> Dict:
        return self._manager.session_stats(session_id)
