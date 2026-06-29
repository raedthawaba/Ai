from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine

logger = logging.getLogger(__name__)

_STRATEGY_PROMPT = """You are an AI exploration strategist. The agent is stuck or underperforming and needs to explore new approaches.

Task Context: {task_context}
Available Tools: {tools}
Recent Failures: {recent_failures}
Agent Confidence: {confidence}

Suggest a novel exploration strategy that avoids the previously failed approaches.
Consider: alternative tool combinations, problem decomposition changes, external information sources.

Respond ONLY with valid JSON:
{{
  "strategy_description": "use tool X combined with Y to approach the problem from angle Z",
  "suggested_actions": [
    "action step 1",
    "action step 2"
  ],
  "rationale": "why this approach might succeed where others failed",
  "estimated_success_prob": 0.65
}}"""

_EVALUATE_EXPLORATION_PROMPT = """Evaluate the outcome of an exploration strategy.

Strategy Used: {strategy}
Exploration Results: {results}

Was the exploration useful? What was learned?

Respond ONLY with valid JSON:
{{
  "evaluation_summary": "summary of what happened",
  "success_score": 3,
  "lessons_learned": ["lesson 1", "lesson 2"],
  "worth_repeating": false
}}"""


class CuriosityEngine:
    """
    Guides agents to explore new actions and strategies when confidence is
    low or repeated failures are detected.
    """

    def __init__(
        self,
        llm_inference_function: Callable,
        reflection_engine: SelfReflectionEngine,
        episodic_memory: EpisodicMemory,
        exploration_threshold: float = 0.3,
        failure_threshold: int = 2,
    ) -> None:
        self.llm_inference_function = llm_inference_function
        self.reflection_engine = reflection_engine
        self.episodic_memory = episodic_memory
        self.exploration_threshold = exploration_threshold
        self.failure_threshold = failure_threshold
        logger.info("CuriosityEngine initialised (threshold=%.2f).", exploration_threshold)

    async def decide_to_explore(
        self,
        current_task_context: Dict[str, Any],
        agent_confidence: float,
        recent_failures: int = 0,
    ) -> bool:
        """Return True if the agent should enter an exploration phase."""
        if agent_confidence < self.exploration_threshold:
            logger.info("Exploration triggered: low confidence (%.2f).", agent_confidence)
            return True
        if recent_failures >= self.failure_threshold:
            logger.info("Exploration triggered: %d recent failures.", recent_failures)
            return True

        # Check novelty: is this task type unseen in episodic memory?
        prompt_key = str(current_task_context.get("prompt", ""))[:80]
        similar = self.episodic_memory.retrieve_experiences(prompt_key, top_k=3)
        if not similar:
            logger.info("Exploration triggered: novel task with no prior experience.")
            return True

        return False

    async def suggest_exploration_strategy(
        self,
        current_task_context: Dict[str, Any],
        available_tools: List[str],
    ) -> Dict[str, Any]:
        """Generate a novel exploration strategy using the LLM."""
        failed_exps = self.episodic_memory.get_failed_experiences(top_k=3)
        failed_summary = [e.get("outcome", "")[:100] for e in failed_exps]

        prompt = _STRATEGY_PROMPT.format(
            task_context=json.dumps(current_task_context)[:600],
            tools=", ".join(available_tools),
            recent_failures=json.dumps(failed_summary),
            confidence=current_task_context.get("confidence", "unknown"),
        )

        logger.info("Generating exploration strategy…")
        return await self._call_and_parse(
            prompt,
            fallback={
                "strategy_description": "Try a different combination of tools.",
                "suggested_actions": ["Decompose the problem differently.", "Seek more context."],
                "rationale": "Fallback strategy — LLM unavailable.",
                "estimated_success_prob": 0.5,
            },
        )

    async def evaluate_exploration_outcome(
        self,
        exploration_strategy: Dict[str, Any],
        exploration_results: str,
    ) -> Dict[str, Any]:
        """Evaluate what was learned from an exploration phase."""
        prompt = _EVALUATE_EXPLORATION_PROMPT.format(
            strategy=json.dumps(exploration_strategy)[:400],
            results=exploration_results[:600],
        )
        logger.info("Evaluating exploration outcome…")
        return await self._call_and_parse(
            prompt,
            fallback={
                "evaluation_summary": "Evaluation unavailable.",
                "success_score": 1,
                "lessons_learned": [],
                "worth_repeating": False,
            },
        )

    # ── Private ─────────────────────────────────────────────────────────

    async def _call_and_parse(
        self, prompt: str, fallback: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            raw = await self.llm_inference_function(prompt)
            parsed = self._parse_json(raw)
            if parsed:
                return parsed
        except Exception as exc:
            logger.error("CuriosityEngine LLM call failed: %s", exc)
        return fallback

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
