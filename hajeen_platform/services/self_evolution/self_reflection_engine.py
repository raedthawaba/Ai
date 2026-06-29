from __future__ import annotations
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class SelfReflectionEngine:
    """Engine for agents to perform self-reflection and critique their own outputs or plans."""

    def __init__(self, llm_inference_function: Callable):
        self.llm_inference_function = llm_inference_function # Function to call LLM for reflection
        logger.info("SelfReflectionEngine initialized.")

    async def reflect_on_output(self, original_prompt: str, agent_output: str, criteria: List[str]) -> Dict[str, Any]:
        """Guides an LLM to reflect on an agent's output based on given criteria."""
        reflection_prompt = f"""You are an AI assistant tasked with critically evaluating another AI agent's output.
Original Prompt: {original_prompt}
Agent's Output: {agent_output}

Evaluate the agent's output based on the following criteria: {', '.join(criteria)}.
Provide a score (1-5, 5 being best) for each criterion and an overall critique.
Also, suggest improvements if any.

Format your response as a JSON object with 'scores', 'critique', and 'improvements' keys.
"""
        
        logger.info("Initiating reflection on agent output...")
        try:
            reflection_response = await self.llm_inference_function(reflection_prompt)
            # Assuming reflection_response is a string that needs parsing
            # In a real system, ensure the LLM returns valid JSON
            import json
            reflection_data = json.loads(reflection_response)
            logger.info("Reflection completed successfully.")
            return reflection_data
        except Exception as e:
            logger.error(f"Error during self-reflection: {e}")
            return {"error": str(e), "critique": "Failed to perform self-reflection.", "scores": {}, "improvements": []}

    async def critique_plan(self, original_goal: str, agent_plan: List[str], criteria: List[str]) -> Dict[str, Any]:
        """Guides an LLM to critique an agent's plan based on given criteria."""
        plan_str = "\n".join([f"- {step}" for step in agent_plan])
        critique_prompt = f"""You are an AI assistant tasked with critically evaluating another AI agent's plan.
Original Goal: {original_goal}
Agent's Plan:
{plan_str}

Evaluate the agent's plan based on the following criteria: {', '.join(criteria)}.
Provide a score (1-5, 5 being best) for each criterion and an overall critique.
Also, suggest improvements to the plan if any.

Format your response as a JSON object with 'scores', 'critique', and 'improvements' keys.
"""
        
        logger.info("Initiating plan critique...")
        try:
            critique_response = await self.llm_inference_function(critique_prompt)
            import json
            critique_data = json.loads(critique_response)
            logger.info("Plan critique completed successfully.")
            return critique_data
        except Exception as e:
            logger.error(f"Error during plan critique: {e}")
            return {"error": str(e), "critique": "Failed to critique plan.", "scores": {}, "improvements": []}

class MockLLM:
    async def __call__(self, prompt: str) -> str:
        if "critically evaluating another AI agent's output" in prompt:
            return '{"scores": {"accuracy": 4, "completeness": 3}, "critique": "Output was mostly accurate but lacked some details.", "improvements": ["Add more details to X."]}'
        elif "critically evaluating another AI agent's plan" in prompt:
            return '{"scores": {"logic": 4, "efficiency": 3}, "critique": "Plan is logical but could be more efficient.", "improvements": ["Combine steps Y and Z."]}'
        return '{"response": "Mock LLM response."}'

print("Self-reflection and critique engine created.")
