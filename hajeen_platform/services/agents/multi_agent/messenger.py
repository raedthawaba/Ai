from __future__ import annotations
import logging
from typing import Dict, Any, List, Optional, Callable
import asyncio

logger = logging.getLogger(__name__)

class AgentMessenger:
    """Handles direct messaging between agents."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._message_history: List[Dict] = []
        self._lock = asyncio.Lock()

    async def subscribe(self, agent_id: str, callback: Callable):
        async with self._lock:
            if agent_id not in self._subscribers:
                self._subscribers[agent_id] = []
            self._subscribers[agent_id].append(callback)
            logger.info(f"Agent {agent_id} subscribed to messenger.")

    async def send_direct(self, from_agent: str, to_agent: str, message: Any):
        async with self._lock:
            msg_obj = {
                "from": from_agent,
                "to": to_agent,
                "content": message,
                "type": "direct"
            }
            self._message_history.append(msg_obj)
            logger.info(f"Message from {from_agent} to {to_agent}: {message}")
            
            if to_agent in self._subscribers:
                for callback in self._subscribers[to_agent]:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(msg_obj)
                    else:
                        callback(msg_obj)

    async def broadcast(self, from_agent: str, message: Any):
        async with self._lock:
            msg_obj = {
                "from": from_agent,
                "to": "all",
                "content": message,
                "type": "broadcast"
            }
            self._message_history.append(msg_obj)
            logger.info(f"Broadcast from {from_agent}: {message}")
            
            for agent_id, callbacks in self._subscribers.items():
                if agent_id != from_agent:
                    for callback in callbacks:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(msg_obj)
                        else:
                            callback(msg_obj)
