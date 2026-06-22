from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_agent import AgentContext, AgentResult, AgentStep, BaseAgent

logger = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    """Agent with persistent cross-session memory capabilities."""

    def __init__(self, memory_service: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(name="memory", description="Manages persistent memory", **kwargs)
        self._memory_svc = memory_service

    async def _execute(self, context: AgentContext) -> AgentResult:
        steps: List[AgentStep] = []

        recalled = await self._recall_relevant(context.goal, context.session_id)
        if recalled:
            context.memory["recalled"] = recalled
            steps.append(
                AgentStep(
                    action="recall_memory",
                    observation=f"Recalled {len(recalled)} memory items",
                    result=recalled,
                )
            )

        response = await self._process_with_memory(context)
        steps.append(
            AgentStep(action="process", observation="Processed with memory context", result=response)
        )

        await self._store_interaction(context, response)
        steps.append(AgentStep(action="store_memory", observation="Interaction stored"))

        return AgentResult(success=True, output=response, steps=steps, context=context)

    async def _recall_relevant(self, query: str, session_id: str) -> Dict:
        if self._memory_svc is None:
            return {}
        try:
            history = self._memory_svc.get_context(session_id, last_n=10)
            preferences = self._memory_svc.recall(session_id, "preferences", {})
            return {"history": history, "preferences": preferences}
        except Exception as exc:
            logger.warning("Memory recall failed: %s", exc)
            return {}

    async def _process_with_memory(self, context: AgentContext) -> str:
        recalled = context.memory.get("recalled", {})
        history = recalled.get("history", [])
        if history:
            recent = history[-3:]
            history_str = "\n".join(f"{m['role']}: {m['content'][:100]}" for m in recent)
            return f"Based on your conversation history:\n{history_str}\n\nRegarding: {context.goal}"
        return f"Processing: {context.goal}"

    async def _store_interaction(self, context: AgentContext, response: str) -> None:
        if self._memory_svc is None:
            return
        try:
            self._memory_svc.add_user_message(context.session_id, context.goal)
            self._memory_svc.add_assistant_message(context.session_id, response)
        except Exception as exc:
            logger.warning("Memory store failed: %s", exc)
