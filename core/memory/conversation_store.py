from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConversationTurn:
    __slots__ = ("role", "content", "timestamp", "metadata")

    def __init__(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        self.role = role
        self.content = content
        self.timestamp = time.time()
        self.metadata: Dict = metadata or {}

    def to_dict(self) -> Dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ConversationTurn":
        obj = cls(d["role"], d["content"], d.get("metadata", {}))
        obj.timestamp = d.get("timestamp", time.time())
        return obj


class ConversationStore:
    """Persistent conversation history store backed by JSONL files."""

    def __init__(self, storage_dir: str = "storage_data/conversations") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[ConversationTurn]] = {}

    def _path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_")
        return self.storage_dir / f"{safe}.jsonl"

    def append(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        turn = ConversationTurn(role, content, metadata)
        if session_id not in self._cache:
            self._cache[session_id] = []
        self._cache[session_id].append(turn)
        self._persist_turn(session_id, turn)

    def get_history(self, session_id: str, last_n: Optional[int] = None) -> List[Dict]:
        if session_id not in self._cache:
            self._load_from_disk(session_id)
        turns = self._cache.get(session_id, [])
        if last_n:
            turns = turns[-last_n:]
        return [t.to_dict() for t in turns]

    def get_messages(self, session_id: str, last_n: Optional[int] = None) -> List[Dict]:
        history = self.get_history(session_id, last_n)
        return [{"role": h["role"], "content": h["content"]} for h in history]

    def clear(self, session_id: str) -> None:
        self._cache.pop(session_id, None)
        p = self._path(session_id)
        if p.exists():
            p.unlink()

    def _persist_turn(self, session_id: str, turn: ConversationTurn) -> None:
        p = self._path(session_id)
        try:
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("Failed to persist turn for %s: %s", session_id, exc)

    def _load_from_disk(self, session_id: str) -> None:
        p = self._path(session_id)
        if not p.exists():
            self._cache[session_id] = []
            return
        turns: List[ConversationTurn] = []
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    turns.append(ConversationTurn.from_dict(json.loads(line)))
        except Exception as exc:
            logger.error("Error loading conversation for %s: %s", session_id, exc)
        self._cache[session_id] = turns
