from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_OUTPUT_REFLECTION_PROMPT = """You are an expert AI evaluator performing self-reflection on an agent's output.

Original Prompt: {original_prompt}

Agent Output:
{agent_output}

Evaluation Criteria: {criteria}

Instructions:
- Score each criterion from 1 (very poor) to 5 (excellent)
- Be honest and critical — inflated scores are harmful
- Provide a concise overall critique
- Suggest concrete improvements

Respond ONLY with valid JSON:
{{
  "scores": {{
    "accuracy": 4,
    "completeness": 3,
    "relevance": 5
  }},
  "overall_score": 4.0,
  "critique": "The output was accurate but missed several edge cases. The response structure was clear.",
  "improvements": [
    "Add handling for edge case X",
    "Reduce verbosity in section Y"
  ],
  "should_retry": false
}}"""

_PLAN_CRITIQUE_PROMPT = """You are an AI agent reviewing a plan before it is executed.

Goal: {goal}

Proposed Plan:
{plan_str}

Evaluation Criteria: {criteria}

Check for:
- Circular or missing dependencies
- Wrong tool assignments
- Missing steps that would prevent goal completion
- Inefficiencies or redundant steps

Respond ONLY with valid JSON:
{{
  "scores": {{
    "logic": 4,
    "efficiency": 3,
    "completeness": 5
  }},
  "overall_score": 4.0,
  "critique": "Plan is logically sound but step 3 could be parallelised with step 2.",
  "improvements": [
    "Merge steps 2 and 3",
    "Add a verification step after step 4"
  ],
  "plan_approved": true
}}"""


class SelfReflectionEngine:
    """
    Engine for agents to perform self-reflection and critique of their own
    outputs and plans using an LLM inference function.
    """

    def __init__(self, llm_inference_function: Callable) -> None:
        self.llm_inference_function = llm_inference_function
        self._history: List[Dict[str, Any]] = []
        logger.info("SelfReflectionEngine initialised.")

    async def reflect_on_output(
        self,
        original_prompt: str,
        agent_output: str,
        criteria: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate an agent's output against given criteria using LLM self-reflection.
        Returns scores, critique, improvements, and a should_retry flag.
        """
        criteria = criteria or ["accuracy", "completeness", "relevance"]
        prompt = _OUTPUT_REFLECTION_PROMPT.format(
            original_prompt=original_prompt[:600],
            agent_output=agent_output[:800],
            criteria=", ".join(criteria),
        )
        logger.info("Reflecting on agent output for prompt: %s…", original_prompt[:60])
        result = await self._call_and_parse(prompt)
        self._history.append({"type": "output_reflection", "result": result})
        return result

    async def critique_plan(
        self,
        original_goal: str,
        agent_plan: List[str],
        criteria: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a plan (list of step strings) before execution.
        Returns scores, critique, improvements, and plan_approved flag.
        """
        criteria = criteria or ["logic", "efficiency", "completeness"]
        plan_str = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(agent_plan))
        prompt = _PLAN_CRITIQUE_PROMPT.format(
            goal=original_goal[:400],
            plan_str=plan_str[:1200],
            criteria=", ".join(criteria),
        )
        logger.info("Critiquing plan for goal: %s…", original_goal[:60])
        result = await self._call_and_parse(prompt)
        self._history.append({"type": "plan_critique", "result": result})
        return result

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Private ─────────────────────────────────────────────────────────

    async def _call_and_parse(self, prompt: str) -> Dict[str, Any]:
        try:
            raw = await self.llm_inference_function(prompt)
            parsed = self._parse_json(raw)
            if parsed:
                return parsed
            logger.warning("SelfReflectionEngine: LLM returned unparseable JSON — using fallback.")
        except Exception as exc:
            logger.error("SelfReflectionEngine LLM call failed: %s", exc)
        return self._fallback_response()

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
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
    def _fallback_response() -> Dict[str, Any]:
        return {
            "scores": {},
            "overall_score": 0.0,
            "critique": "Reflection unavailable — LLM call failed.",
            "improvements": ["Retry the reflection when LLM is available."],
            "should_retry": False,
            "plan_approved": True,
        }
