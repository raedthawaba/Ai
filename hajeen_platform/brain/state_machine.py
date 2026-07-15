"""
State Machine — آلة الحالات لدورة حياة المهام
===============================================
كل مهمة تمتلك دورة حياة كاملة من الانتظار حتى الاكتمال أو الاسترداد.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    WAITING = "waiting"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    RETRY = "retry"
    FAILED = "failed"
    COMPLETED = "completed"
    RECOVERED = "recovered"


VALID_TRANSITIONS: Dict[TaskState, List[TaskState]] = {
    TaskState.WAITING: [TaskState.PLANNING, TaskState.FAILED],
    TaskState.PLANNING: [TaskState.RUNNING, TaskState.FAILED],
    TaskState.RUNNING: [TaskState.PAUSED, TaskState.COMPLETED, TaskState.FAILED, TaskState.RETRY],
    TaskState.PAUSED: [TaskState.RUNNING, TaskState.FAILED],
    TaskState.RETRY: [TaskState.RUNNING, TaskState.FAILED],
    TaskState.FAILED: [TaskState.RECOVERED],
    TaskState.COMPLETED: [],
    TaskState.RECOVERED: [TaskState.PLANNING],
}


@dataclass
class TaskLifecycle:
    task_id: str
    state: TaskState = TaskState.WAITING
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def can_transition_to(self, new_state: TaskState) -> bool:
        return new_state in VALID_TRANSITIONS.get(self.state, [])

    def transition(self, new_state: TaskState, reason: str = "") -> bool:
        if not self.can_transition_to(new_state):
            logger.warning(
                "state_machine: Invalid transition %s → %s for task %s",
                self.state, new_state, self.task_id
            )
            return False
        old_state = self.state
        self.state = new_state
        self.updated_at = time.time()
        self.transitions.append({
            "from": old_state,
            "to": new_state,
            "at": self.updated_at,
            "reason": reason,
        })
        logger.info(
            "state_machine: task=%s %s → %s (%s)",
            self.task_id, old_state, new_state, reason
        )
        return True

    def should_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        self.retry_count += 1
        self.transition(TaskState.RETRY, f"retry #{self.retry_count}")


class StateMachine:
    """
    مدير آلات الحالة لجميع المهام النشطة.
    يتتبع كل مهمة ويسمح بالانتقال بين الحالات بأمان.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskLifecycle] = {}
        self._hooks: Dict[TaskState, List[Callable]] = {}
        self._lock = asyncio.Lock()

    def create_task(
        self,
        task_id: Optional[str] = None,
        max_retries: int = 3,
        metadata: Optional[Dict] = None,
    ) -> TaskLifecycle:
        tid = task_id or str(uuid.uuid4())
        task = TaskLifecycle(
            task_id=tid,
            max_retries=max_retries,
            metadata=metadata or {},
        )
        self._tasks[tid] = task
        logger.info("state_machine: created task=%s", tid)
        return task

    def get_task(self, task_id: str) -> Optional[TaskLifecycle]:
        return self._tasks.get(task_id)

    async def transition(
        self, task_id: str, new_state: TaskState, reason: str = ""
    ) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.error("state_machine: task not found: %s", task_id)
                return False
            success = task.transition(new_state, reason)
            if success:
                await self._run_hooks(new_state, task)
            return success

    def register_hook(self, state: TaskState, hook: Callable) -> None:
        self._hooks.setdefault(state, []).append(hook)

    async def _run_hooks(self, state: TaskState, task: TaskLifecycle) -> None:
        for hook in self._hooks.get(state, []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(task)
                else:
                    hook(task)
            except Exception as e:
                logger.error("state_machine: hook error for state %s: %s", state, e)

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        return [
            {
                "task_id": t.task_id,
                "state": t.state,
                "retry_count": t.retry_count,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "error": t.error,
            }
            for t in self._tasks.values()
        ]

    def get_stats(self) -> Dict[str, int]:
        stats: Dict[str, int] = {s.value: 0 for s in TaskState}
        for t in self._tasks.values():
            stats[t.state] += 1
        return stats


# Singleton
_state_machine: Optional[StateMachine] = None


def get_state_machine() -> StateMachine:
    global _state_machine
    if _state_machine is None:
        _state_machine = StateMachine()
    return _state_machine
