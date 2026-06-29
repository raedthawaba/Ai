from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from hajeen_platform.services.agents.base_agent import AgentContext, AgentResult

logger = logging.getLogger(__name__)

_REFLECTION_PROMPT = """You are a critical self-evaluation engine for an autonomous AI agent.

Goal the agent was trying to achieve:
{goal}

Execution result:
Success: {success}
Output: {output}

Steps taken:
{steps_summary}

Evaluate the execution critically:
1. Did the agent actually achieve the goal?
2. Were the steps efficient and correct?
3. Are there signs of hallucination, wrong assumptions, or tool misuse?
4. Is replanning needed?

Respond ONLY with valid JSON:
{{
  "goal_achieved": true,
  "analysis": "detailed analysis of what happened",
  "issues_found": ["issue 1", "issue 2"],
  "suggestions": ["improvement 1", "improvement 2"],
  "replan_needed": false,
  "replan_reason": "why replan is or is not needed",
  "confidence_score": 0.85
}}"""


class ReflectionLoop:
    """
    Reflection engine that uses an LLM to critically evaluate execution results,
    identify failures, and decide whether replanning is needed.
    """

    def __init__(self, llm: Any) -> None:
        self.llm = llm
        self._reflection_history: List[Dict] = []

    async def reflect(self, current_result: AgentResult, context: AgentContext) -> Dict:
        """
        Analyse the execution result using the LLM. Returns a dict with:
        - goal_achieved (bool)
        - analysis (str)
        - issues_found (list)
        - suggestions (list)
        - replan_needed (bool)
        - confidence_score (float)
        """
        logger.info("Reflecting on execution for session %s", context.session_id)

        steps_summary = self._summarise_steps(current_result)
        prompt = _REFLECTION_PROMPT.format(
            goal=context.goal,
            success=current_result.success,
            output=(current_result.output or "")[:800],
            steps_summary=steps_summary,
        )

        raw = await self._call_llm(prompt)
        reflection = self._parse_json(raw)

        if reflection is None:
            reflection = self._fallback_reflection(current_result)

        self._reflection_history.append(reflection)
        logger.info(
            "Reflection complete — goal_achieved=%s replan_needed=%s confidence=%.2f",
            reflection.get("goal_achieved"),
            reflection.get("replan_needed"),
            reflection.get("confidence_score", 0.0),
        )
        return reflection

    async def critique_plan(self, plan: List[Dict], goal: str) -> Dict:
        """Evaluate a plan before execution to catch obvious issues early."""
        prompt = f"""Critique the following execution plan for the goal: {goal}

Plan:
{json.dumps(plan, indent=2)[:1500]}

Check for: circular dependencies, missing steps, wrong tool assignments, unclear tasks.

Respond with valid JSON:
{{
  "plan_quality": 0.8,
  "issues": ["issue 1"],
  "improvements": ["suggestion 1"],
  "approved": true
}}"""
        raw = await self._call_llm(prompt)
        result = self._parse_json(raw)
        return result or {"plan_quality": 0.5, "issues": [], "improvements": [], "approved": True}

    def get_reflection_history(self) -> List[Dict]:
        return list(self._reflection_history)

    def should_stop(self) -> bool:
        """Detect repeated failures — stop if last 3 reflections all say replan is needed."""
        if len(self._reflection_history) < 3:
            return False
        return all(r.get("replan_needed", False) for r in self._reflection_history[-3:])

    # ── Private helpers ─────────────────────────────────────────────────

    async def _call_llm(self, prompt: str) -> str:
        try:
            if hasattr(self.llm, "agenerate"):
                return await self.llm.agenerate(prompt)
            if hasattr(self.llm, "generate"):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self.llm.generate, prompt)
            if callable(self.llm):
                result = self.llm(prompt)
                return await result if asyncio.iscoroutine(result) else result
        except Exception as exc:
            logger.error("LLM call failed in ReflectionLoop: %s", exc)
        return ""

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict]:
        if not raw:
            return None
        raw = raw.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _summarise_steps(result: AgentResult) -> str:
        if not result.steps:
            return "No steps recorded."
        lines = []
        for i, step in enumerate(result.steps[:10], 1):
            status = "ERROR" if step.error else "OK"
            lines.append(f"  {i}. [{status}] {step.action} → {step.observation or step.error or ''}")
        return "\n".join(lines)

    @staticmethod
    def _fallback_reflection(result: AgentResult) -> Dict:
        return {
            "goal_achieved": result.success,
            "analysis": "LLM reflection unavailable — using execution status as proxy.",
            "issues_found": [result.error] if result.error else [],
            "suggestions": ["Review execution logs for details."],
            "replan_needed": not result.success,
            "replan_reason": result.error or "Execution failed.",
            "confidence_score": 0.9 if result.success else 0.3,
        }
