from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .short_term_memory import ShortTermMemory
from .long_term_memory import LongTermMemory
from .conversation_store import ConversationStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """Unified interface over all memory layers."""

    def __init__(
        self,
        max_short_term_turns: int = 20,
        storage_dir: str = "storage_data",
    ) -> None:
        self.short_term = ShortTermMemory(max_turns=max_short_term_turns)
        self.long_term = LongTermMemory(storage_dir=f"{storage_dir}/long_term_memory")
        self.conversation_store = ConversationStore(storage_dir=f"{storage_dir}/conversations")
        logger.info("MemoryManager initialized")

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        persist: bool = True,
        metadata: Optional[Dict] = None,
    ) -> None:
        self.short_term.add(session_id, role, content, metadata)
        if persist:
            self.conversation_store.append(session_id, role, content, metadata)

    def get_recent_messages(
        self, session_id: str, last_n: int = 20
    ) -> List[Dict]:
        return self.short_term.get_as_messages(session_id, last_n)

    def get_full_history(self, session_id: str) -> List[Dict]:
        return self.conversation_store.get_messages(session_id)

    def remember(self, session_id: str, key: str, value: Any) -> None:
        self.long_term.save(session_id, key, value)

    def recall(self, session_id: str, key: str, default: Any = None) -> Any:
        return self.long_term.load(session_id, key, default)

    def forget(self, session_id: str, key: str) -> bool:
        return self.long_term.delete(session_id, key)

    def clear_session(self, session_id: str) -> None:
        self.short_term.clear(session_id)
        self.long_term.clear_session(session_id)
        self.conversation_store.clear(session_id)
        logger.info("Session cleared: %s", session_id)

    def session_stats(self, session_id: str) -> Dict:
        return {
            "session_id": session_id,
            "short_term_turns": self.short_term.turn_count(session_id),
            "long_term_keys": len(self.long_term.list_keys(session_id)),
        }
