from __future__ import annotations
import asyncio
import logging
from typing import List, Dict, Any, Optional

from hajeen_platform.services.agents.base_agent import BaseAgent, AgentContext, AgentStep, AgentResult
from hajeen_platform.services.agents.autonomous.recursive_planner import RecursivePlanner
from hajeen_platform.services.agents.autonomous.task_executor import TaskExecutor
from hajeen_platform.services.agents.autonomous.reflection_loop import ReflectionLoop

logger = logging.getLogger(__name__)

class AutonomousAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        description: str = "",
        max_iterations: int = 10,
        llm: Optional[Any] = None,
        agent_manager: Optional[Any] = None, # Orchestrator or agent manager
    ) -> None:
        super().__init__(name, description, max_iterations, llm)
        if not llm:
            raise ValueError("LLM must be provided for AutonomousAgent")
        if not agent_manager:
            raise ValueError("Agent manager must be provided for AutonomousAgent")

        self.planner = RecursivePlanner(llm)
        self.executor = TaskExecutor(agent_manager) # Pass agent_manager for tool delegation
        self.reflector = ReflectionLoop(llm)
        logger.info("AutonomousAgent '%s' initialized with planner, executor, and reflector.", name)

    async def _execute(self, context: AgentContext) -> AgentResult:
        logger.info(f"AutonomousAgent '{self.name}' starting execution for goal: {context.goal}")
        current_plan = []
        overall_steps: List[AgentStep] = []

        while not context.is_exhausted():
            context.iterations += 1
            logger.info(f"AutonomousAgent '{self.name}' iteration {context.iterations}/{context.max_iterations}")

            # 1. Planning Phase
            planning_step = AgentStep(action="Planning")
            try:
                current_plan = await self.planner.plan(context.goal, context)
                planning_step.result = {"plan": current_plan}
                planning_step.observation = "Successfully generated a plan."
            except Exception as e:
                planning_step.error = str(e)
                planning_step.observation = f"Planning failed: {e}"
                overall_steps.append(planning_step)
                return AgentResult(success=False, output="Planning failed.", steps=overall_steps, context=context, error=str(e))
            overall_steps.append(planning_step)

            # 2. Execution Phase
            execution_step = AgentStep(action="Executing Plan")
            try:
                execution_result = await self.executor.execute_task_tree(current_plan, context)
                execution_step.result = execution_result.output
                execution_step.observation = f"Plan execution {'succeeded' if execution_result.success else 'failed'}."
                overall_steps.extend(execution_result.steps) # Add sub-steps from execution
            except Exception as e:
                execution_step.error = str(e)
                execution_step.observation = f"Execution failed: {e}"
                overall_steps.append(execution_step)
                return AgentResult(success=False, output="Execution failed.", steps=overall_steps, context=context, error=str(e))
            overall_steps.append(execution_step)

            # 3. Reflection Phase
            reflection_step = AgentStep(action="Reflecting on Execution")
            try:
                reflection_output = await self.reflector.reflect(execution_result, context)
                reflection_step.result = reflection_output
                reflection_step.observation = "Reflection completed."
                if reflection_output.get("replan_needed"):
                    logger.info("Reflection suggests re-planning.")
                    # The loop will continue to the next iteration for re-planning
                else:
                    # If no replanning is needed, we consider the goal achieved for this iteration
                    return AgentResult(success=True, output="Goal achieved through autonomous execution.", steps=overall_steps, context=context)
            except Exception as e:
                reflection_step.error = str(e)
                reflection_step.observation = f"Reflection failed: {e}"
                overall_steps.append(reflection_step)
                # Even if reflection fails, we might still return the execution result if it was successful
                if execution_result.success:
                    return AgentResult(success=True, output="Goal achieved, but reflection encountered an error.", steps=overall_steps, context=context)
                else:
                    return AgentResult(success=False, output="Reflection failed after execution failure.", steps=overall_steps, context=context, error=str(e))
            overall_steps.append(reflection_step)

        return AgentResult(success=False, output="Max iterations reached without achieving goal.", steps=overall_steps, context=context, error="Max iterations reached.")
