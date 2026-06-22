from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from pydantic import BaseModel


class MemoryEntry(BaseModel):
    role: str
    content: str
    timestamp: float
    metadata: Dict = {}


class ShortTermMemory:
    """Sliding-window in-memory conversation buffer per session."""

    def __init__(self, max_turns: int = 20, ttl_seconds: float = 3600.0) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, Deque[MemoryEntry]] = {}
        self._last_access: Dict[str, float] = {}

    def add(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=self.max_turns * 2)
        self._sessions[session_id].append(
            MemoryEntry(
                role=role,
                content=content,
                timestamp=time.time(),
                metadata=metadata or {},
            )
        )
        self._last_access[session_id] = time.time()

    def get(self, session_id: str, last_n: Optional[int] = None) -> List[MemoryEntry]:
        self._evict_stale()
        entries = list(self._sessions.get(session_id, deque()))
        if last_n is not None:
            entries = entries[-last_n:]
        return entries

    def get_as_messages(self, session_id: str, last_n: Optional[int] = None) -> List[Dict]:
        return [{"role": e.role, "content": e.content} for e in self.get(session_id, last_n)]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._last_access.pop(session_id, None)

    def _evict_stale(self) -> None:
        now = time.time()
        stale = [sid for sid, t in self._last_access.items() if now - t > self.ttl_seconds]
        for sid in stale:
            self._sessions.pop(sid, None)
            self._last_access.pop(sid, None)

    def session_count(self) -> int:
        return len(self._sessions)

    def turn_count(self, session_id: str) -> int:
        return len(self._sessions.get(session_id, []))
