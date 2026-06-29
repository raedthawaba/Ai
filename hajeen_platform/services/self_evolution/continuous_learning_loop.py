from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from hajeen_platform.services.self_evolution.curiosity_engine import CuriosityEngine
from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine

logger = logging.getLogger(__name__)


class ContinuousLearningLoop:
    """
    Master coordinator for self-improvement:
    1. Executes a task via the agent
    2. Reflects on the output with SelfReflectionEngine
    3. Stores the experience in EpisodicMemory
    4. Decides whether to explore with CuriosityEngine
    5. Returns a full learning report
    """

    def __init__(
        self,
        llm_inference_function: Callable,
        reflection_engine: SelfReflectionEngine,
        episodic_memory: EpisodicMemory,
        curiosity_engine: CuriosityEngine,
    ) -> None:
        self.llm_inference_function = llm_inference_function
        self.reflection_engine = reflection_engine
        self.episodic_memory = episodic_memory
        self.curiosity_engine = curiosity_engine
        self._cycle_count: int = 0
        logger.info("ContinuousLearningLoop initialised.")

    async def execute_and_learn(
        self,
        task_prompt: str,
        agent_action_function: Callable,
        available_tools: List[str],
        reflection_criteria: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Full learning cycle:
        - Run the agent
        - Reflect on its output
        - Store the experience
        - Optionally trigger exploration
        Returns a comprehensive learning report.
        """
        self._cycle_count += 1
        logger.info("Learning cycle #%d — task: %s", self._cycle_count, task_prompt[:80])

        # ── 1. Execute ───────────────────────────────────────────────────
        try:
            agent_output: Dict[str, Any] = await agent_action_function(task_prompt, available_tools)
        except Exception as exc:
            logger.error("Agent execution failed in learning loop: %s", exc)
            agent_output = {
                "success": False,
                "output": "",
                "confidence": 0.0,
                "actions_taken": [],
                "error": str(exc),
            }

        task_success: bool = agent_output.get("success", False)
        agent_confidence: float = agent_output.get("confidence", 1.0)
        agent_actions: List[str] = agent_output.get("actions_taken", [])
        raw_output: str = agent_output.get("output", "")

        # ── 2. Self-reflection ───────────────────────────────────────────
        criteria = reflection_criteria or ["accuracy", "completeness", "relevance"]
        reflection_result = await self.reflection_engine.reflect_on_output(
            original_prompt=task_prompt,
            agent_output=raw_output,
            criteria=criteria,
        )
        logger.debug("Reflection scores: %s", reflection_result.get("scores", {}))

        # Downgrade success if reflection finds critical issues
        overall_score = reflection_result.get("overall_score", 0.0)
        if overall_score and overall_score < 2.5:
            task_success = False
            logger.info("Reflection downgraded success to False (score=%.1f).", overall_score)

        # ── 3. Store experience ──────────────────────────────────────────
        self.episodic_memory.add_experience(
            prompt=task_prompt,
            actions=agent_actions,
            outcome=raw_output,
            success=task_success,
            reflection=reflection_result,
            metadata={
                "confidence": agent_confidence,
                "cycle": self._cycle_count,
                "tools_available": available_tools,
            },
        )

        # ── 4. Curiosity / exploration decision ─────────────────────────
        recent_failures = len(self.episodic_memory.get_failed_experiences(top_k=5))
        should_explore = await self.curiosity_engine.decide_to_explore(
            current_task_context={
                "prompt": task_prompt,
                "output": raw_output[:200],
                "confidence": agent_confidence,
            },
            agent_confidence=agent_confidence,
            recent_failures=recent_failures,
        )

        exploration_result: Optional[Dict[str, Any]] = None
        if should_explore:
            logger.info("Curiosity triggered — generating exploration strategy.")
            strategy = await self.curiosity_engine.suggest_exploration_strategy(
                current_task_context={
                    "prompt": task_prompt,
                    "output": raw_output[:200],
                },
                available_tools=available_tools,
            )
            # Store the exploration intent as a separate memory entry
            self.episodic_memory.add_experience(
                prompt=f"[EXPLORATION] {task_prompt}",
                actions=strategy.get("suggested_actions", []),
                outcome=strategy.get("strategy_description", ""),
                success=False,
                metadata={"type": "exploration_strategy", "cycle": self._cycle_count},
            )
            exploration_result = strategy

        # ── 5. Build report ──────────────────────────────────────────────
        report = {
            "cycle": self._cycle_count,
            "task": task_prompt,
            "task_success": task_success,
            "agent_confidence": agent_confidence,
            "reflection": reflection_result,
            "memory_summary": self.episodic_memory.summary(),
            "exploration_triggered": should_explore,
            "exploration_strategy": exploration_result,
            "status": "exploration_suggested" if should_explore else "completed",
        }
        logger.info(
            "Learning cycle #%d complete — success=%s explore=%s",
            self._cycle_count, task_success, should_explore,
        )
        return report

    def get_cycle_count(self) -> int:
        return self._cycle_count

    def get_learning_summary(self) -> Dict[str, Any]:
        return {
            "total_cycles": self._cycle_count,
            "memory_summary": self.episodic_memory.summary(),
        }
