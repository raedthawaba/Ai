from __future__ import annotations
import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class MemoryEntry:
    agent_id: str
    content: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

class SharedMemoryBus:
    """A shared communication and state bus for multiple agents."""
    
    def __init__(self):
        self._entries: List[MemoryEntry] = []
        self._kv_store: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        logger.info("SharedMemoryBus initialized.")

    async def post_message(self, agent_id: str, content: Any, metadata: Optional[Dict] = None):
        async with self._lock:
            entry = MemoryEntry(agent_id=agent_id, content=content, metadata=metadata or {})
            self._entries.append(entry)
            logger.debug(f"Agent {agent_id} posted to bus: {content}")

    async def get_messages(self, limit: int = 10) -> List[MemoryEntry]:
        async with self._lock:
            return self._entries[-limit:]

    async def set_state(self, key: str, value: Any):
        async with self._lock:
            self._kv_store[key] = value

    async def get_state(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._kv_store.get(key, default)

    def clear(self):
        self._entries = []
        self._kv_store = {}
