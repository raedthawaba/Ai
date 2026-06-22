from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Type

from .base_agent import AgentContext, AgentResult, BaseAgent
from .planner_agent import PlannerAgent
from .retrieval_agent import RetrievalAgent
from .execution_agent import ExecutionAgent
from .memory_agent import MemoryAgent
from .tool_agent import ToolAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates multiple agents in a pipeline to complete complex goals."""

    def __init__(
        self,
        llm: Optional[Any] = None,
        rag_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        max_iterations: int = 10,
    ) -> None:
        self._llm = llm
        self._rag = rag_service
        self._memory_svc = memory_service
        self.max_iterations = max_iterations
        self._agents: Dict[str, BaseAgent] = {}
        self._pipeline: List[str] = []
        self._build_default_pipeline()

    def _build_default_pipeline(self) -> None:
        self._agents["planner"] = PlannerAgent(llm=self._llm, max_iterations=self.max_iterations)
        self._agents["retrieval"] = RetrievalAgent(rag_service=self._rag)
        self._agents["execution"] = ExecutionAgent(llm=self._llm, max_iterations=self.max_iterations)
        if self._memory_svc:
            self._agents["memory"] = MemoryAgent(memory_service=self._memory_svc)
        self._pipeline = ["planner", "retrieval", "execution"]

    def register_agent(self, name: str, agent: BaseAgent) -> None:
        self._agents[name] = agent
        logger.info("Agent registered in orchestrator: %s", name)

    def set_pipeline(self, pipeline: List[str]) -> None:
        unknown = [n for n in pipeline if n not in self._agents]
        if unknown:
            raise ValueError(f"Unknown agents in pipeline: {unknown}")
        self._pipeline = pipeline

    async def run(
        self,
        goal: str,
        session_id: Optional[str] = None,
        pipeline: Optional[List[str]] = None,
    ) -> Dict:
        active_pipeline = pipeline or self._pipeline
        context = AgentContext(
            goal=goal,
            session_id=session_id or "",
            max_iterations=self.max_iterations,
        )

        results: List[AgentResult] = []
        all_steps: List[Dict] = []
        final_output = ""

        for agent_name in active_pipeline:
            agent = self._agents.get(agent_name)
            if agent is None:
                logger.warning("Agent '%s' not found, skipping", agent_name)
                continue

            logger.info("Running agent: %s", agent_name)
            result = await agent.run(goal=goal, context=context)
            results.append(result)

            if result.output:
                final_output = result.output
                context.memory[f"{agent_name}_output"] = result.output

            for step in result.steps:
                all_steps.append(
                    {
                        "agent": agent_name,
                        "action": step.action,
                        "observation": step.observation,
                        "tool": step.tool_used,
                        "error": step.error,
                    }
                )

            if not result.success and result.error:
                logger.error("Agent '%s' failed: %s", agent_name, result.error)
                break

        return {
            "goal": goal,
            "output": final_output,
            "agents_run": [r.context.session_id if r.context else "" for r in results],
            "total_steps": len(all_steps),
            "steps": all_steps,
            "success": all(r.success for r in results),
            "elapsed_ms": round(context.elapsed() * 1000, 2),
        }

    async def parallel_run(self, goals: List[str]) -> List[Dict]:
        tasks = [self.run(goal) for goal in goals]
        return await asyncio.gather(*tasks, return_exceptions=False)
