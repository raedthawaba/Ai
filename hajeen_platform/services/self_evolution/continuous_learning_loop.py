from __future__ import annotations
import logging
from typing import Dict, Any, List, Callable, Optional
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine
from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory
from hajeen_platform.services.self_evolution.curiosity_engine import CuriosityEngine

logger = logging.getLogger(__name__)

class ContinuousLearningLoop:
    """Orchestrates self-reflection, episodic memory, and curiosity to enable continuous self-improvement."""

    def __init__(self, 
                 llm_inference_function: Callable,
                 reflection_engine: SelfReflectionEngine,
                 episodic_memory: EpisodicMemory,
                 curiosity_engine: CuriosityEngine):
        self.llm_inference_function = llm_inference_function
        self.reflection_engine = reflection_engine
        self.episodic_memory = episodic_memory
        self.curiosity_engine = curiosity_engine
        logger.info("ContinuousLearningLoop initialized.")

    async def execute_and_learn(self, 
                                task_prompt: str, 
                                agent_action_function: Callable,
                                available_tools: List[str]) -> Dict[str, Any]:
        """Executes a task, then triggers a learning cycle based on the outcome."""
        logger.info(f"Starting execution and learning cycle for task: {task_prompt}")

        # 1. Agent executes the task
        initial_agent_output = await agent_action_function(task_prompt, available_tools)
        task_success = initial_agent_output.get("success", False)
        agent_confidence = initial_agent_output.get("confidence", 1.0) # Assume high confidence by default
        agent_actions = initial_agent_output.get("actions_taken", [])

        # 2. Self-reflection on the output
        reflection_result = await self.reflection_engine.reflect_on_output(
            original_prompt=task_prompt,
            agent_output=initial_agent_output.get("output", ""),
            criteria=["accuracy", "completeness", "relevance"]
        )
        logger.debug(f"Reflection result: {reflection_result}")

        # Update task success based on reflection if available
        if reflection_result.get("scores", {}).get("accuracy", 0) < 3:
            task_success = False

        # 3. Store experience in episodic memory
        self.episodic_memory.add_experience(
            prompt=task_prompt,
            actions=agent_actions,
            outcome=initial_agent_output.get("output", ""),
            success=task_success,
            reflection=reflection_result,
            metadata={"confidence": agent_confidence}
        )
        logger.info(f"Experience stored. Task success: {task_success}")

        # 4. Decide if exploration is needed
        recent_failures = len(self.episodic_memory.get_failed_experiences(top_k=5))
        should_explore = await self.curiosity_engine.decide_to_explore(
            current_task_context={"prompt": task_prompt, "output": initial_agent_output.get("output", "")},
            agent_confidence=agent_confidence,
            recent_failures=recent_failures
        )

        if should_explore:
            logger.info("Exploration triggered.")
            exploration_strategy = await self.curiosity_engine.suggest_exploration_strategy(
                current_task_context={"prompt": task_prompt, "output": initial_agent_output.get("output", "")},
                available_tools=available_tools
            )
            # In a real scenario, the agent would then execute this strategy
            # For now, we just log it and store it as part of the experience
            logger.info(f"Suggested exploration strategy: {exploration_strategy}")
            # Optionally, store exploration as a separate experience or update current one
            self.episodic_memory.add_experience(
                prompt=f"Exploration for: {task_prompt}",
                actions=exploration_strategy.get("suggested_actions", []),
                outcome=exploration_strategy.get("strategy_description", ""),
                success=False, # Exploration is not a direct task success, but a learning step
                metadata={"type": "exploration_strategy"}
            )
            return {"status": "exploration_suggested", "original_output": initial_agent_output, "reflection": reflection_result, "exploration_strategy": exploration_strategy}
        else:
            logger.info("No exploration needed.")
            return {"status": "completed", "original_output": initial_agent_output, "reflection": reflection_result}

print("Continuous learning loop component created.")
