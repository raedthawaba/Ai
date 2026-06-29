from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from hajeen_platform.services.agents.base_agent import (
    AgentContext,
    AgentResult,
    AgentStep,
    BaseAgent,
)
from hajeen_platform.services.agents.multi_agent.messenger import AgentMessenger
from hajeen_platform.services.agents.multi_agent.shared_memory import SharedMemoryBus

logger = logging.getLogger(__name__)


class CollaborativeIntelligence:
    """
    Orchestrates collaborative behaviour between multiple agents:
    - Broadcast goals and proposals via AgentMessenger
    - Share intermediate state via SharedMemoryBus
    - Assign tasks based on agent specialisation
    - Cross-review results before accepting
    - Synthesise a consensus answer
    """

    def __init__(self, agents: List[BaseAgent]) -> None:
        self.agents = agents
        self.memory_bus = SharedMemoryBus()
        self.messenger = AgentMessenger()
        self._inject_collaborative_capabilities()
        logger.info(
            "CollaborativeIntelligence initialised with %d agents: %s",
            len(agents),
            [a.name for a in agents],
        )

    # ── Public API ────────────────────────────────────────────────────────

    async def collaborative_solve(
        self, goal: str, context: AgentContext
    ) -> AgentResult:
        """
        Full collaborative problem-solving cycle:
        1. Broadcast the goal
        2. Collect proposals from every agent
        3. Assign specialised sub-tasks
        4. Cross-review results
        5. Synthesise and return the final answer
        """
        logger.info("Collaborative session started — goal: %s", goal[:80])
        all_steps: List[AgentStep] = []

        # ── 1. Broadcast ──────────────────────────────────────────────────
        await self.messenger.broadcast("system", f"Collaborative goal received: {goal}")
        await self.memory_bus.set_state("goal", goal)

        # ── 2. Proposal phase ─────────────────────────────────────────────
        proposals: List[Dict[str, Any]] = []
        proposal_tasks = [self._get_proposal(agent, goal, context) for agent in self.agents]
        proposal_results = await asyncio.gather(*proposal_tasks, return_exceptions=False)

        for agent, proposal in zip(self.agents, proposal_results):
            proposals.append(proposal)
            await self.memory_bus.post_message(agent.name, f"Proposal: {proposal}")
            all_steps.append(
                AgentStep(
                    action=f"[{agent.name}] submitted proposal",
                    observation=str(proposal),
                )
            )

        # ── 3. Task assignment ────────────────────────────────────────────
        assignments = self._assign_tasks(proposals)
        execution_results: List[Dict[str, Any]] = []

        for assignment in assignments:
            executor = self._find_agent(assignment.get("agent"))
            if executor is None:
                continue
            sub_task = assignment.get("task", goal)
            logger.info("Delegating sub-task '%s' to %s", sub_task[:60], executor.name)

            await self.messenger.send_direct(
                "system", executor.name, f"Execute: {sub_task}"
            )
            try:
                result = await executor.run(sub_task, context)
                execution_results.append(
                    {"agent": executor.name, "task": sub_task, "result": result, "success": result.success}
                )
                await self.memory_bus.set_state(f"{executor.name}_result", result.output)
                all_steps.append(
                    AgentStep(
                        action=f"[{executor.name}] executed task",
                        observation=result.output[:200] if result.output else "no output",
                    )
                )
            except Exception as exc:
                logger.error("Agent %s failed on task: %s", executor.name, exc)
                execution_results.append(
                    {"agent": executor.name, "task": sub_task, "result": None, "success": False, "error": str(exc)}
                )

        # ── 4. Cross-review ───────────────────────────────────────────────
        reviews: List[str] = []
        for exec_res in execution_results:
            if not exec_res["success"] or exec_res["result"] is None:
                continue
            reviewer = self._pick_reviewer(exec_res["agent"])
            review = await self._review_result(reviewer, exec_res["result"])
            reviews.append(f"{reviewer.name} reviewed {exec_res['agent']}: {review}")
            all_steps.append(
                AgentStep(
                    action=f"[{reviewer.name}] reviewed {exec_res['agent']}'s output",
                    observation=review,
                )
            )

        # ── 5. Synthesis ──────────────────────────────────────────────────
        final_output = self._synthesise(goal, execution_results, reviews)
        overall_success = any(r["success"] for r in execution_results)

        logger.info("Collaborative session complete — success=%s", overall_success)
        return AgentResult(
            success=overall_success,
            output=final_output,
            steps=all_steps,
            context=context,
        )

    async def parallel_vote(
        self, goal: str, context: AgentContext
    ) -> AgentResult:
        """
        Have all agents independently answer the goal, then vote on the best answer.
        Useful for factual queries or when consensus matters.
        """
        logger.info("Parallel vote started — goal: %s", goal[:80])
        tasks = [agent.run(goal, context) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Majority vote on success
        successes = [r for r in results if r.success]
        if not successes:
            return AgentResult(
                success=False,
                output="All agents failed to answer.",
                context=context,
            )

        # Pick the longest (most detailed) successful answer as winner
        best = max(successes, key=lambda r: len(r.output or ""))
        votes = f"{len(successes)}/{len(self.agents)} agents succeeded."

        return AgentResult(
            success=True,
            output=f"{best.output}\n\n[Consensus: {votes}]",
            context=context,
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _inject_collaborative_capabilities(self) -> None:
        for agent in self.agents:
            setattr(agent, "memory_bus", self.memory_bus)
            setattr(agent, "messenger", self.messenger)

    async def _get_proposal(
        self, agent: BaseAgent, goal: str, context: AgentContext
    ) -> Dict[str, Any]:
        try:
            proposal_goal = (
                f"Briefly describe how you (as {agent.name}) would approach this goal. "
                f"Goal: {goal}"
            )
            result = await agent.run(proposal_goal, context)
            return {
                "agent": agent.name,
                "task": result.output[:300] if result.output else goal,
                "confidence": 0.8 if result.success else 0.3,
            }
        except Exception as exc:
            return {"agent": agent.name, "task": goal, "confidence": 0.1, "error": str(exc)}

    def _assign_tasks(self, proposals: List[Dict]) -> List[Dict]:
        """Assign one proposal per agent (round-robin by confidence)."""
        sorted_props = sorted(proposals, key=lambda p: p.get("confidence", 0), reverse=True)
        # Each agent gets at most one task
        seen: set = set()
        assignments = []
        for prop in sorted_props:
            agent_name = prop.get("agent", "")
            if agent_name not in seen:
                assignments.append(prop)
                seen.add(agent_name)
        return assignments

    def _find_agent(self, name: Optional[str]) -> Optional[BaseAgent]:
        if not name:
            return self.agents[0] if self.agents else None
        return next((a for a in self.agents if a.name == name), None)

    def _pick_reviewer(self, executor_name: str) -> BaseAgent:
        for agent in self.agents:
            if agent.name != executor_name:
                return agent
        return self.agents[0]

    async def _review_result(self, reviewer: BaseAgent, result: AgentResult) -> str:
        review_goal = (
            f"Briefly critique this output in 1-2 sentences: {result.output[:300]}"
        )
        try:
            review = await reviewer.run(review_goal)
            return review.output[:200] if review.output else "Looks acceptable."
        except Exception:
            return "Review unavailable."

    @staticmethod
    def _synthesise(
        goal: str,
        results: List[Dict[str, Any]],
        reviews: List[str],
    ) -> str:
        successful = [r for r in results if r["success"] and r["result"] is not None]
        if not successful:
            return f"Collaborative solving failed for goal: {goal}"

        parts = [f"Collaborative Result for: {goal}\n"]
        for r in successful:
            parts.append(f"— {r['agent']}: {r['result'].output[:300]}")
        if reviews:
            parts.append("\nPeer Reviews:")
            parts.extend(f"  • {rev}" for rev in reviews)
        return "\n".join(parts)
