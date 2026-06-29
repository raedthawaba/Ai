from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

from hajeen_platform.services.agents.base_agent import AgentContext, AgentResult, AgentStep

logger = logging.getLogger(__name__)


class TaskExecutor:
    """
    Executes a task tree produced by RecursivePlanner.
    Supports:
    - Dependency-aware topological execution
    - Parallel execution of independent tasks
    - Tool dispatch via agent_manager or registered tools
    - Per-task retry with configurable attempts
    - Failure detection and error propagation
    """

    MAX_RETRIES: int = 2
    RETRY_DELAY_S: float = 0.5

    def __init__(self, agent_manager: Any, tools: Optional[Dict[str, Callable]] = None) -> None:
        self.agent_manager = agent_manager
        self._tools: Dict[str, Callable] = tools or {}

    def register_tool(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn

    async def execute_task_tree(
        self, task_tree: List[Dict], context: AgentContext
    ) -> AgentResult:
        """
        Execute tasks in dependency order.  Tasks with no shared dependencies
        are executed in parallel.  Returns a merged AgentResult.
        """
        logger.info(
            "TaskExecutor starting — %d tasks for session %s",
            len(task_tree),
            context.session_id,
        )
        if not task_tree:
            return AgentResult(success=True, output="No tasks to execute.", context=context)

        # Build execution graph
        graph = self._build_graph(task_tree)
        completed: Set[str] = set()
        all_steps: List[AgentStep] = []
        outputs: Dict[str, Any] = {}
        overall_success = True
        error_msg: Optional[str] = None

        while True:
            ready = [
                node
                for nid, node in graph.items()
                if nid not in completed and node.get("status") == "pending"
                and all(dep in completed for dep in node.get("depends_on", []))
            ]
            if not ready:
                break

            # Execute all ready tasks in parallel
            tasks_coros = [
                self._execute_single(node, context, outputs) for node in ready
            ]
            results = await asyncio.gather(*tasks_coros, return_exceptions=False)

            for node, (step, output, success) in zip(ready, results):
                all_steps.append(step)
                node["status"] = "done" if success else "failed"
                completed.add(node["id"])
                if output is not None:
                    outputs[node["id"]] = output
                    context.memory[f"task_{node['id']}_output"] = str(output)[:500]
                if not success:
                    overall_success = False
                    error_msg = step.error
                    logger.warning("Task %s failed: %s", node["id"], step.error)

        final_output = self._synthesise_output(context.goal, outputs, all_steps)
        return AgentResult(
            success=overall_success,
            output=final_output,
            steps=all_steps,
            context=context,
            error=error_msg,
        )

    # ── Private helpers ─────────────────────────────────────────────────

    async def _execute_single(
        self, node: Dict, context: AgentContext, prior_outputs: Dict[str, Any]
    ):
        task_desc = node.get("task", "unknown task")
        tool_name = node.get("tool", "llm")
        step = AgentStep(action=f"[{node['id']}] {task_desc}", tool_used=tool_name)
        start = time.perf_counter()

        enriched_input = self._enrich_with_prior(task_desc, node.get("depends_on", []), prior_outputs)

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                output = await self._dispatch(tool_name, enriched_input, context)
                step.result = output
                step.observation = f"Task '{task_desc[:60]}' completed successfully."
                step.duration_ms = round((time.perf_counter() - start) * 1000, 2)
                return step, output, True
            except Exception as exc:
                logger.warning("Task %s attempt %d failed: %s", node["id"], attempt + 1, exc)
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_DELAY_S * (attempt + 1))
                else:
                    step.error = str(exc)
                    step.observation = f"Task '{task_desc[:60]}' failed after {self.MAX_RETRIES + 1} attempts."
                    step.duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    return step, None, False

    async def _dispatch(self, tool_name: str, task_input: str, context: AgentContext) -> Any:
        """Route the task to the appropriate tool or agent."""
        # 1. Check registered tools first
        if tool_name in self._tools:
            fn = self._tools[tool_name]
            if asyncio.iscoroutinefunction(fn):
                return await fn(task_input)
            return fn(task_input)

        # 2. Try agent_manager's registered agents
        if hasattr(self.agent_manager, "_agents"):
            agent = self.agent_manager._agents.get(tool_name)
            if agent:
                result = await agent.run(goal=task_input, context=context)
                return result.output

        # 3. Delegate to LLM via agent_manager
        if hasattr(self.agent_manager, "_llm") and self.agent_manager._llm:
            llm = self.agent_manager._llm
            if hasattr(llm, "agenerate"):
                return await llm.agenerate(task_input)
            if hasattr(llm, "generate"):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, llm.generate, task_input)

        # 4. Fallback: mark as acknowledged
        logger.warning("No executor found for tool '%s' — task acknowledged.", tool_name)
        return f"[Acknowledged] {task_input}"

    @staticmethod
    def _build_graph(tasks: List[Dict]) -> Dict[str, Dict]:
        graph: Dict[str, Dict] = {}
        for t in tasks:
            node = dict(t)
            node.setdefault("status", "pending")
            graph[node["id"]] = node
        return graph

    @staticmethod
    def _enrich_with_prior(task: str, depends_on: List[str], outputs: Dict[str, Any]) -> str:
        if not depends_on or not outputs:
            return task
        prior_info = []
        for dep_id in depends_on:
            if dep_id in outputs:
                prior_info.append(f"Output of {dep_id}: {str(outputs[dep_id])[:300]}")
        if prior_info:
            return f"{task}\n\nContext from prior steps:\n" + "\n".join(prior_info)
        return task

    @staticmethod
    def _synthesise_output(goal: str, outputs: Dict[str, Any], steps: List[AgentStep]) -> str:
        if not outputs:
            return f"Execution completed for: {goal}"
        last_output = list(outputs.values())[-1]
        if isinstance(last_output, str):
            return last_output
        return f"Goal: {goal}\n\nFinal result:\n{str(last_output)}"
