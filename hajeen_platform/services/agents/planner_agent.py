from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .base_agent import AgentContext, AgentResult, AgentStep, BaseAgent

logger = logging.getLogger(__name__)

_PLANNING_PROMPT = """You are a planning agent. Break the following goal into a numbered list of concrete steps.
Output JSON with this format: {{"steps": ["step 1", "step 2", ...]}}

Goal: {goal}

Steps (JSON only):"""


class PlannerAgent(BaseAgent):
    """Decomposes complex goals into actionable step sequences."""

    def __init__(self, llm: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(name="planner", description="Decomposes goals into steps", llm=llm, **kwargs)

    async def _execute(self, context: AgentContext) -> AgentResult:
        steps_taken: List[AgentStep] = []

        plan = await self._generate_plan(context.goal)
        steps_taken.append(
            AgentStep(
                action="generate_plan",
                observation=f"Generated {len(plan)} steps",
                result=plan,
            )
        )

        context.memory["plan"] = plan
        output = self._format_plan(plan)

        return AgentResult(
            success=True,
            output=output,
            steps=steps_taken,
            context=context,
        )

    async def _generate_plan(self, goal: str) -> List[str]:
        if self._llm is not None:
            try:
                from core.inference_engine import InferenceConfig
                prompt = _PLANNING_PROMPT.format(goal=goal)
                text = await self._llm.agenerate(prompt, config=InferenceConfig(max_new_tokens=512, temperature=0.3))
                parsed = json.loads(text.strip())
                return parsed.get("steps", [])
            except Exception as exc:
                logger.warning("LLM planning failed: %s. Using heuristic fallback.", exc)

        return self._heuristic_plan(goal)

    @staticmethod
    def _heuristic_plan(goal: str) -> List[str]:
        steps = [
            f"Understand the goal: {goal}",
            "Gather relevant information",
            "Identify key sub-tasks",
            "Execute each sub-task in order",
            "Verify results and summarize",
        ]
        return steps

    @staticmethod
    def _format_plan(steps: List[str]) -> str:
        lines = ["**Execution Plan:**"]
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        return "\n".join(lines)
