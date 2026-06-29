from __future__ import annotations
import logging
import asyncio
from typing import List, Dict, Any, Optional
from .shared_memory import SharedMemoryBus
from .messenger import AgentMessenger
from ..base_agent import BaseAgent, AgentContext, AgentResult

logger = logging.getLogger(__name__)

class CollaborativeIntelligence:
    """Orchestrates collaborative behavior between agents."""
    
    def __init__(self, agents: List[BaseAgent]):
        self.agents = agents
        self.memory_bus = SharedMemoryBus()
        self.messenger = AgentMessenger()
        self._setup_collaborations()

    def _setup_collaborations(self):
        for agent in self.agents:
            # Inject collaborative capabilities into agents
            setattr(agent, 'memory_bus', self.memory_bus)
            setattr(agent, 'messenger', self.messenger)
            # Agents can now use self.messenger.send_direct(...) or self.memory_bus.post_message(...)

    async def collaborative_solve(self, goal: str, context: AgentContext) -> AgentResult:
        logger.info(f"Starting collaborative session for goal: {goal}")
        
        # 1. Discussion Phase
        await self.messenger.broadcast("system", f"New collaborative goal: {goal}")
        
        # 2. Shared Planning
        # In a real scenario, agents would propose sub-tasks
        # Here we simulate a consensus-based planning
        plan_proposals = []
        for agent in self.agents:
            # Each agent contributes to the plan based on its specialty
            proposal = await self._get_agent_proposal(agent, goal, context)
            plan_proposals.append(proposal)
            await self.memory_bus.post_message(agent.name, f"Proposed: {proposal}")

        # 3. Execution with review
        results = []
        for proposal in plan_proposals:
            target_agent = self._route_to_specialist(proposal)
            if target_agent:
                res = await target_agent.run(proposal["task"], context)
                # Review by another agent
                reviewer = self._get_reviewer(target_agent)
                review = await self._review_result(reviewer, res)
                results.append({"agent": target_agent.name, "result": res, "review": review})

        # 4. Final Synthesis
        final_output = self._synthesize_results(results)
        
        return AgentResult(
            success=True,
            output=final_output,
            steps=[], # Simplified for this stage
            context=context
        )

    async def _get_agent_proposal(self, agent: BaseAgent, goal: str, context: AgentContext) -> Dict:
        # Simulate agent thinking about the goal
        return {"task": f"Specialized sub-task for {agent.name}", "confidence": 0.9}

    def _route_to_specialist(self, proposal: Dict) -> Optional[BaseAgent]:
        # Simple routing logic
        return self.agents[0] if self.agents else None

    def _get_reviewer(self, executor: BaseAgent) -> BaseAgent:
        # Get a different agent to review
        for agent in self.agents:
            if agent.name != executor.name:
                return agent
        return executor

    async def _review_result(self, reviewer: BaseAgent, result: AgentResult) -> str:
        return f"Reviewed by {reviewer.name}: Looks good."

    def _synthesize_results(self, results: List[Dict]) -> str:
        summary = "Collaborative Output:\n"
        for r in results:
            summary += f"- {r['agent']}: {r['result'].output} (Review: {r['review']})\n"
        return summary
