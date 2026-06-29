from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from hajeen_platform.services.agents.base_agent import AgentContext, AgentStep

logger = logging.getLogger(__name__)

_DECOMPOSE_PROMPT = """You are an expert autonomous planning agent. Decompose the following goal into a structured task tree.

Goal: {goal}

Prior context:
{context_str}

Available tools: {tools}

Rules:
- Each task must be atomic and independently verifiable
- Use depends_on to express true data dependencies (task IDs that must finish first)
- Assign the most suitable tool per task
- Prioritize tasks by execution order (1 = first)

Respond ONLY with valid JSON (no markdown fences):
{{
  "tasks": [
    {{
      "id": "t1",
      "task": "exact description of action to perform",
      "tool": "llm|search|code_exec|file_io|retrieval",
      "depends_on": [],
      "expected_output": "what success looks like",
      "priority": 1
    }},
    {{
      "id": "t2",
      "task": "next action",
      "tool": "llm",
      "depends_on": ["t1"],
      "expected_output": "result description",
      "priority": 2
    }}
  ],
  "goal_summary": "one-line plan summary",
  "estimated_steps": 2
}}"""

_REPLAN_PROMPT = """A plan failed during execution. Produce a revised plan that avoids the same failure.

Original Goal: {goal}
Failed Plan:
{original_plan}

Failure Details: {failure_details}
Already Completed Tasks: {completed_steps}

Instructions:
1. Analyse WHY the plan failed
2. Generate revised tasks only for REMAINING work (skip completed ones)
3. Be more specific and defensive in the new steps

Respond ONLY with valid JSON:
{{
  "failure_analysis": "root cause explanation",
  "revised_tasks": [
    {{
      "id": "r1",
      "task": "revised task description",
      "tool": "llm|search|code_exec|file_io|retrieval",
      "depends_on": [],
      "expected_output": "success criterion",
      "priority": 1
    }}
  ],
  "strategy_change": "what is different in this approach"
}}"""


@dataclass
class TaskNode:
    id: str
    task: str
    tool: str
    depends_on: List[str] = field(default_factory=list)
    expected_output: str = ""
    priority: int = 1
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None

    def is_ready(self, completed_ids: Set[str]) -> bool:
        return all(dep in completed_ids for dep in self.depends_on)


class RecursivePlanner:
    """
    Recursive planning engine that uses an LLM to decompose goals into
    structured task trees with dependency tracking and adaptive replanning.
    """

    def __init__(self, llm: Any) -> None:
        self.llm = llm
        self._last_plan: List[Dict] = []
        self._replan_count: int = 0
        self._max_replans: int = 3

    # ── Public API ──────────────────────────────────────────────────────

    async def plan(
        self,
        goal: str,
        context: AgentContext,
        available_tools: Optional[List[str]] = None,
    ) -> List[Dict]:
        tools_str = ", ".join(
            available_tools or ["llm", "search", "code_exec", "file_io", "retrieval"]
        )
        context_str = self._build_context_str(context)
        task_tree = await self._generate_task_tree(goal, context_str, tools_str)
        self._last_plan = task_tree
        self._replan_count = 0
        logger.info("Planner produced %d tasks for: %s", len(task_tree), goal[:80])
        return task_tree

    async def replan(
        self,
        goal: str,
        context: AgentContext,
        failure_details: str,
        completed_steps: List[str],
    ) -> List[Dict]:
        if self._replan_count >= self._max_replans:
            logger.warning("Max replans (%d) reached — returning fallback plan.", self._max_replans)
            return self._minimal_fallback_plan(goal)

        self._replan_count += 1
        logger.info("Replanning (attempt %d/%d).", self._replan_count, self._max_replans)

        prompt = _REPLAN_PROMPT.format(
            goal=goal,
            original_plan=json.dumps(self._last_plan, indent=2)[:1200],
            failure_details=failure_details,
            completed_steps=json.dumps(completed_steps),
        )
        raw = await self._call_llm(prompt)
        parsed = self._parse_json(raw)

        if not parsed or "revised_tasks" not in parsed:
            return self._minimal_fallback_plan(goal)

        self._last_plan = parsed["revised_tasks"]
        logger.info("Replan strategy: %s", parsed.get("strategy_change", "—"))
        return self._last_plan

    def build_execution_graph(self, tasks: List[Dict]) -> Dict[str, TaskNode]:
        graph: Dict[str, TaskNode] = {}
        for idx, t in enumerate(tasks):
            node = TaskNode(
                id=t.get("id", f"task_{idx}"),
                task=t.get("task", ""),
                tool=t.get("tool", "llm"),
                depends_on=t.get("depends_on", []),
                expected_output=t.get("expected_output", ""),
                priority=t.get("priority", idx + 1),
            )
            graph[node.id] = node
        return graph

    def get_ready_tasks(
        self, graph: Dict[str, TaskNode], completed_ids: Set[str]
    ) -> List[TaskNode]:
        return sorted(
            [n for n in graph.values() if n.status == "pending" and n.is_ready(completed_ids)],
            key=lambda n: n.priority,
        )

    # ── Private helpers ──────────────────────────────────────────────────

    async def _generate_task_tree(self, goal: str, context_str: str, tools_str: str) -> List[Dict]:
        prompt = _DECOMPOSE_PROMPT.format(goal=goal, context_str=context_str, tools=tools_str)
        raw = await self._call_llm(prompt)
        parsed = self._parse_json(raw)
        if parsed and isinstance(parsed.get("tasks"), list) and parsed["tasks"]:
            return parsed["tasks"]
        logger.warning("LLM returned invalid plan — falling back to heuristic decomposition.")
        return self._heuristic_decompose(goal)

    async def _call_llm(self, prompt: str) -> str:
        try:
            if hasattr(self.llm, "agenerate"):
                return await self.llm.agenerate(prompt)
            if hasattr(self.llm, "generate"):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self.llm.generate, prompt)
            if callable(self.llm):
                result = self.llm(prompt)
                return await result if asyncio.iscoroutine(result) else result
        except Exception as exc:
            logger.error("LLM call failed in RecursivePlanner: %s", exc)
        return ""

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict]:
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

    @staticmethod
    def _build_context_str(context: AgentContext) -> str:
        parts = [f"  {k}: {str(v)[:200]}" for k, v in list(context.memory.items())[:5]]
        return "\n".join(parts) if parts else "No prior context."

    @staticmethod
    def _heuristic_decompose(goal: str) -> List[Dict]:
        return [
            {"id": "t1", "task": f"Analyse and understand the goal: {goal}", "tool": "llm",
             "depends_on": [], "expected_output": "Clear understanding of requirements", "priority": 1},
            {"id": "t2", "task": "Gather relevant context and information", "tool": "retrieval",
             "depends_on": ["t1"], "expected_output": "Relevant facts and data collected", "priority": 2},
            {"id": "t3", "task": "Execute the core action based on analysis", "tool": "llm",
             "depends_on": ["t2"], "expected_output": "Primary task completed with output", "priority": 3},
            {"id": "t4", "task": "Verify results and synthesise final answer", "tool": "llm",
             "depends_on": ["t3"], "expected_output": "Verified, coherent final answer", "priority": 4},
        ]

    @staticmethod
    def _minimal_fallback_plan(goal: str) -> List[Dict]:
        return [{"id": "fallback_1", "task": f"Best-effort completion of: {goal}", "tool": "llm",
                 "depends_on": [], "expected_output": "Partial or best-effort result", "priority": 1}]
