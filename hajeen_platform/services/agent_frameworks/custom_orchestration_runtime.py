from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── State Machine ────────────────────────────────────────────────────────────

class WorkflowStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class WorkflowState:
    workflow_id: str
    current_state: str
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None

    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 3)


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    action: Optional[Callable] = None


# ── Workflow Definition ──────────────────────────────────────────────────────

@dataclass
class WorkflowDefinition:
    workflow_id: str
    initial_state: str
    states: Dict[str, Callable]           # state_name -> async handler(ctx) -> str (next state)
    transitions: List[StateTransition] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)   # legacy sequential tasks
    terminal_states: List[str] = field(default_factory=lambda: ["done", "end", "failed"])
    max_state_hops: int = 50
    on_error: Optional[Callable] = None


# ── Runtime ──────────────────────────────────────────────────────────────────

class CustomOrchestrationRuntime:
    """
    Dynamic execution engine for goal-driven multi-agent orchestration.
    Supports:
    - State machine execution (dynamic, conditional state transitions)
    - Sequential and parallel task graphs
    - Event-driven workflows
    - Multi-agent coordination
    - Retry and error recovery
    """

    def __init__(self, agent_registry: Dict[str, Any]) -> None:
        self._agent_registry = agent_registry
        self._workflow_definitions: Dict[str, WorkflowDefinition] = {}
        self._active_workflows: Dict[str, WorkflowState] = {}
        self._event_listeners: Dict[str, List[Callable]] = {}
        logger.info("CustomOrchestrationRuntime initialised with %d agents.", len(agent_registry))

    # ── Registration ────────────────────────────────────────────────────

    def register_workflow(self, definition: WorkflowDefinition) -> None:
        """Register a workflow definition by its ID."""
        self._workflow_definitions[definition.workflow_id] = definition
        logger.info("Workflow '%s' registered (states: %s).", definition.workflow_id,
                    list(definition.states.keys()))

    def register_agent(self, name: str, agent: Any) -> None:
        """Register or replace an agent in the runtime."""
        self._agent_registry[name] = agent
        logger.info("Agent '%s' registered in runtime.", name)

    def on_event(self, event_name: str, handler: Callable) -> None:
        """Subscribe a handler to a named event."""
        self._event_listeners.setdefault(event_name, []).append(handler)

    # ── Execution ────────────────────────────────────────────────────────

    async def execute_workflow(
        self, workflow_id: str, initial_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a registered workflow.  Supports both:
        - State-machine mode (WorkflowDefinition.states populated)
        - Sequential task-graph mode (WorkflowDefinition.tasks populated)
        """
        definition = self._workflow_definitions.get(workflow_id)
        if not definition:
            raise ValueError(f"Workflow '{workflow_id}' not registered.")

        run_id = str(uuid.uuid4())[:8]
        state = WorkflowState(
            workflow_id=workflow_id,
            current_state=definition.initial_state,
            context=dict(initial_context),
            started_at=time.time(),
            status=WorkflowStatus.RUNNING,
        )
        self._active_workflows[run_id] = state
        logger.info("Workflow '%s' run %s started.", workflow_id, run_id)

        await self._emit_event("workflow_started", {"workflow_id": workflow_id, "run_id": run_id})

        try:
            if definition.states:
                result = await self._run_state_machine(definition, state)
            else:
                result = await self._run_task_graph(definition, state)

            state.status = WorkflowStatus.COMPLETED
            state.finished_at = time.time()
            await self._emit_event("workflow_completed", {"workflow_id": workflow_id, "run_id": run_id})
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "status": "completed",
                "final_state": state.current_state,
                "context": state.context,
                "steps": state.history,
                "elapsed_s": state.elapsed(),
                "result": result,
            }
        except Exception as exc:
            state.status = WorkflowStatus.FAILED
            state.error = str(exc)
            state.finished_at = time.time()
            logger.error("Workflow '%s' run %s failed: %s", workflow_id, run_id, exc)
            if definition.on_error:
                try:
                    await definition.on_error(state, exc)
                except Exception:
                    pass
            await self._emit_event("workflow_failed", {"workflow_id": workflow_id, "run_id": run_id, "error": str(exc)})
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(exc),
                "elapsed_s": state.elapsed(),
            }

    async def coordinate_agents(
        self, agent_names: List[str], goal: str, parallel: bool = False
    ) -> Dict[str, Any]:
        """Coordinate a group of agents toward a shared goal."""
        logger.info("Coordinating agents %s for goal: %s", agent_names, goal[:60])
        results: Dict[str, Any] = {}

        if parallel:
            tasks = {
                name: self._run_agent(name, goal)
                for name in agent_names
                if name in self._agent_registry
            }
            gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for name, res in zip(tasks.keys(), gathered):
                results[name] = str(res) if isinstance(res, Exception) else res
        else:
            for name in agent_names:
                results[name] = await self._run_agent(name, goal)

        return results

    def list_workflows(self) -> List[str]:
        return list(self._workflow_definitions.keys())

    def get_active_workflows(self) -> Dict[str, Dict]:
        return {
            run_id: {
                "workflow_id": ws.workflow_id,
                "status": ws.status.name,
                "current_state": ws.current_state,
                "elapsed_s": ws.elapsed(),
            }
            for run_id, ws in self._active_workflows.items()
        }

    # ── Private: State Machine ───────────────────────────────────────────

    async def _run_state_machine(
        self, definition: WorkflowDefinition, state: WorkflowState
    ) -> Any:
        hops = 0
        while state.current_state not in definition.terminal_states:
            if hops >= definition.max_state_hops:
                raise RuntimeError(
                    f"State machine exceeded max hops ({definition.max_state_hops})"
                )
            handler = definition.states.get(state.current_state)
            if handler is None:
                raise ValueError(f"No handler for state '{state.current_state}'")

            step_start = time.time()
            next_state = await handler(state.context)
            duration = round((time.time() - step_start) * 1000, 2)

            state.history.append({
                "from": state.current_state,
                "to": next_state,
                "duration_ms": duration,
            })
            logger.debug("State transition: %s → %s (%.0f ms)", state.current_state, next_state, duration)
            state.current_state = next_state
            hops += 1

        return state.context.get("result")

    # ── Private: Task Graph ──────────────────────────────────────────────

    async def _run_task_graph(
        self, definition: WorkflowDefinition, state: WorkflowState
    ) -> Any:
        completed: set = set()
        outputs: Dict[str, Any] = {}

        while True:
            ready = [
                t for t in definition.tasks
                if t.get("id") not in completed
                and all(dep in completed for dep in t.get("depends_on", []))
            ]
            if not ready:
                break

            # Run independent tasks in parallel
            batch_results = await asyncio.gather(
                *[self._execute_task(t, state, outputs) for t in ready],
                return_exceptions=False,
            )
            for task, (tid, output, ok) in zip(ready, batch_results):
                completed.add(tid)
                if output is not None:
                    outputs[tid] = output
                    state.context[f"{tid}_output"] = output
                state.history.append({"task_id": tid, "success": ok, "output": str(output)[:200]})

        state.context["outputs"] = outputs
        return outputs

    async def _execute_task(
        self, task: Dict, state: WorkflowState, prior_outputs: Dict
    ):
        tid = task.get("id", "unknown")
        agent_name = task.get("agent", "")
        goal = task.get("goal", task.get("input", ""))

        # Enrich goal with prior outputs
        deps = task.get("depends_on", [])
        if deps:
            ctx_parts = [f"{d}: {str(prior_outputs.get(d, ''))[:200]}" for d in deps if d in prior_outputs]
            if ctx_parts:
                goal = f"{goal}\n\nPrior context:\n" + "\n".join(ctx_parts)

        try:
            output = await self._run_agent(agent_name, goal)
            return tid, output, True
        except Exception as exc:
            logger.error("Task '%s' (agent=%s) failed: %s", tid, agent_name, exc)
            return tid, None, False

    async def _run_agent(self, agent_name: str, goal: str) -> Any:
        agent = self._agent_registry.get(agent_name)
        if agent is None:
            raise ValueError(f"Agent '{agent_name}' not found in registry.")
        result = await agent.run(goal=goal)
        return result.output if hasattr(result, "output") else result

    async def _emit_event(self, event_name: str, payload: Dict) -> None:
        for handler in self._event_listeners.get(event_name, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as exc:
                logger.warning("Event handler for '%s' failed: %s", event_name, exc)
