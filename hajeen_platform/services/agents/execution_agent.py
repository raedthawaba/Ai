from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base_agent import AgentContext, AgentResult, AgentStep, BaseAgent

logger = logging.getLogger(__name__)


class ExecutionAgent(BaseAgent):
    """Executes a plan step-by-step, calling tools as needed."""

    def __init__(self, llm: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(
            name="execution",
            description="Executes multi-step plans with tool usage",
            llm=llm,
            **kwargs,
        )

    async def _execute(self, context: AgentContext) -> AgentResult:
        plan: List[str] = context.memory.get("plan", [context.goal])
        steps_taken: List[AgentStep] = []
        results: List[str] = []

        for step_description in plan:
            if context.is_exhausted():
                break
            context.iterations += 1

            step = await self._execute_step(step_description, context)
            steps_taken.append(step)

            if step.error:
                logger.warning("Step failed: %s — %s", step_description, step.error)
            else:
                results.append(str(step.result or step.observation))

        output = self._synthesize(context.goal, results)
        return AgentResult(
            success=len([s for s in steps_taken if not s.error]) > 0,
            output=output,
            steps=steps_taken,
            context=context,
        )

    async def _execute_step(self, description: str, context: AgentContext) -> AgentStep:
        tool_name = self._identify_tool(description)
        if tool_name and tool_name in self._tools:
            try:
                result = await self._call_tool(tool_name, query=description)
                return AgentStep(
                    action=description,
                    tool_used=tool_name,
                    result=result,
                    observation=f"Tool '{tool_name}' executed successfully",
                )
            except Exception as exc:
                return AgentStep(action=description, tool_used=tool_name, error=str(exc))

        if self._llm is not None:
            try:
                from core.inference_engine import InferenceConfig
                context_str = "\n".join(f"- {r}" for r in list(context.memory.get("tool_results", []))[:3])
                prompt = (
                    f"Complete this task step:\n{description}\n\n"
                    f"Previous context:\n{context_str}\n\nResult:"
                )
                text = await self._llm.agenerate(
                    prompt, config=InferenceConfig(max_new_tokens=256, temperature=0.5)
                )
                return AgentStep(action=description, result=text, observation="LLM response generated")
            except Exception as exc:
                return AgentStep(action=description, error=str(exc), observation="LLM failed")

        return AgentStep(
            action=description,
            result=f"Step '{description}' completed",
            observation="No executor available, step marked done",
        )

    def _identify_tool(self, description: str) -> Optional[str]:
        desc_lower = description.lower()
        for tool_name in self._tools:
            if tool_name.lower() in desc_lower:
                return tool_name
        return None

    @staticmethod
    def _synthesize(goal: str, results: List[str]) -> str:
        if not results:
            return f"Could not complete goal: {goal}"
        return f"Goal accomplished: {goal}\n\nSummary:\n" + "\n".join(f"• {r}" for r in results)
