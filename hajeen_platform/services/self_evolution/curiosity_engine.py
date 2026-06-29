from __future__ import annotations
import logging
from typing import Dict, Any, List, Callable, Optional
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine
from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory
import json

logger = logging.getLogger(__name__)

class CuriosityEngine:
    """Guides agents to explore new actions, tools, or strategies when current approaches are insufficient."""

    def __init__(self, 
                 llm_inference_function: Callable,
                 reflection_engine: SelfReflectionEngine,
                 episodic_memory: EpisodicMemory,
                 exploration_threshold: float = 0.3):
        self.llm_inference_function = llm_inference_function
        self.reflection_engine = reflection_engine
        self.episodic_memory = episodic_memory
        self.exploration_threshold = exploration_threshold # e.g., confidence score below this triggers exploration
        logger.info("CuriosityEngine initialized.")

    async def decide_to_explore(self, 
                                current_task_context: Dict[str, Any],
                                agent_confidence: float,
                                recent_failures: int = 0) -> bool:
        """Decides if an agent should initiate an exploration phase."""
        if agent_confidence < self.exploration_threshold:
            logger.info(f"Low confidence ({agent_confidence}) detected. Suggesting exploration.")
            return True
        
        # Check for repeated failures on similar tasks
        if recent_failures > 2: # Arbitrary threshold for demonstration
            logger.info(f"Repeated failures ({recent_failures}) detected. Suggesting exploration.")
            return True

        # Placeholder for novelty detection (e.g., if task is completely new or unusual)
        # This would involve comparing current task to past experiences in episodic memory
        # For now, a simple check for low confidence or failures is used.
        
        logger.debug("No strong reason to explore based on current metrics.")
        return False

    async def suggest_exploration_strategy(self, 
                                           current_task_context: Dict[str, Any],
                                           available_tools: List[str]) -> Dict[str, Any]:
        """Suggests new tools, actions, or approaches for exploration based on context."""
        exploration_prompt = f"""Given the current task context and available tools, suggest a novel exploration strategy.
Task Context: {json.dumps(current_task_context, indent=2)}
Available Tools: {', '.join(available_tools)}

Consider strategies like:
- Trying a different combination of existing tools.
- Breaking down the problem into smaller, unconventional sub-problems.
- Seeking external information from a broader source.
- Re-evaluating assumptions about the task.

Provide a JSON object with 'strategy_description' and 'suggested_actions' (list of strings).
"""
        logger.info("Generating exploration strategy...")
        try:
            strategy_response = await self.llm_inference_function(exploration_prompt)

            strategy_data = json.loads(strategy_response)
            logger.info("Exploration strategy generated.")
            return strategy_data
        except Exception as e:
            logger.error(f"Error generating exploration strategy: {e}")
            return {"error": str(e), "strategy_description": "Failed to generate strategy.", "suggested_actions": []}

    async def evaluate_exploration_outcome(self, 
                                           exploration_strategy: Dict[str, Any],
                                           exploration_results: str) -> Dict[str, Any]:
        """Evaluates the outcome of an exploration phase using the reflection engine."""
        evaluation_prompt = f"""Evaluate the effectiveness of the following exploration strategy and its results.
Exploration Strategy: {json.dumps(exploration_strategy, indent=2)}
Exploration Results: {exploration_results}

Critique the exploration: Was it successful? Did it yield useful insights? How could it be improved?
Provide a JSON object with 'evaluation_summary', 'success_score' (1-5), and 'lessons_learned' (list of strings).
"""
        logger.info("Evaluating exploration outcome...")
        # Use the reflection engine's LLM call for this, or a direct LLM call
        try:
            evaluation_response = await self.llm_inference_function(evaluation_prompt)

            evaluation_data = json.loads(evaluation_response)
            logger.info("Exploration outcome evaluated.")
            return evaluation_data
        except Exception as e:
            logger.error(f"Error evaluating exploration outcome: {e}")
            return {"error": str(e), "evaluation_summary": "Failed to evaluate outcome.", "success_score": 1, "lessons_learned": []}



print("Curiosity and exploration engine created.")
