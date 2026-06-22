"""Priority Queue System — section 6.7.

Pure-Python priority queue using ``heapq``.

Features:
- Priority insertion (lower value = higher priority)
- Task ordering by priority then submission time
- Queue inspection (peek, size, list)
- Delayed tasks (not ready until a given timestamp)
- High-priority constants

Thread-safe via threading.Lock.
"""
from __future__ import annotations

import heapq
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterator, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

class Priority(IntEnum):
    CRITICAL = 0
    HIGH     = 10
    NORMAL   = 50
    LOW      = 100
    IDLE     = 200


# ---------------------------------------------------------------------------
# Task item
# ---------------------------------------------------------------------------

@dataclass(order=True)
class PriorityTask:
    """A task with priority, timestamp, and optional delay.

    Ordering: lower priority value → higher urgency.
    Ties broken by ``sequence`` (FIFO).
    """
    priority: int                  # compared first
    sequence: int                  # compared second (insertion order)
    ready_at: float = field(compare=True)  # epoch timestamp when task becomes runnable
    task_id: str = field(compare=False)
    name: str = field(compare=False)
    payload: Any = field(compare=False, default=None)
    created_at: float = field(compare=False, default_factory=time.time)

    @property
    def is_ready(self) -> bool:
        """True when the task delay has elapsed."""
        return time.time() >= self.ready_at

    def __repr__(self) -> str:
        return (
            f"PriorityTask(id={self.task_id!r} name={self.name!r} "
            f"priority={self.priority} ready_at={self.ready_at:.2f})"
        )


# ---------------------------------------------------------------------------
# Priority Queue
# ---------------------------------------------------------------------------

class PriorityTaskQueue:
    """Thread-safe priority task queue.

    Parameters
    ----------
    max_size:
        Optional maximum number of tasks. ``None`` = unlimited.
    """

    def __init__(self, max_size: Optional[int] = None) -> None:
        self._heap: List[PriorityTask] = []
        self._lock = threading.Lock()
        self._sequence = 0
        self.max_size = max_size

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def push(
        self,
        name: str,
        payload: Any = None,
        priority: int = Priority.NORMAL,
        delay_seconds: float = 0.0,
        task_id: Optional[str] = None,
    ) -> PriorityTask:
        """Add a task to the queue.

        Parameters
        ----------
        name:
            Human-readable task name.
        payload:
            Arbitrary task data.
        priority:
            Urgency level — lower value = higher priority.
        delay_seconds:
            Seconds to wait before the task becomes eligible.
        task_id:
            Optional explicit task ID (auto-generated when omitted).

        Returns
        -------
        The created :class:`PriorityTask`.

        Raises
        ------
        OverflowError:
            When ``max_size`` is set and the queue is full.
        """
        with self._lock:
            if self.max_size is not None and len(self._heap) >= self.max_size:
                raise OverflowError(
                    f"PriorityTaskQueue is full (max_size={self.max_size})"
                )
            seq = self._sequence
            self._sequence += 1
            task = PriorityTask(
                priority=priority,
                sequence=seq,
                ready_at=time.time() + delay_seconds,
                task_id=task_id or str(uuid.uuid4()),
                name=name,
                payload=payload,
            )
            heapq.heappush(self._heap, task)
            logger.debug(
                "PriorityQueue: pushed %r priority=%d delay=%.1fs",
                name, priority, delay_seconds,
            )
            return task

    def pop(self, block_timeout: Optional[float] = None) -> Optional[PriorityTask]:
        """Remove and return the highest-priority ready task.

        Parameters
        ----------
        block_timeout:
            If set, poll for up to this many seconds until a ready task appears.
            If ``None``, returns immediately (``None`` if none ready).

        Returns
        -------
        :class:`PriorityTask` or ``None``.
        """
        deadline = time.time() + (block_timeout or 0)
        while True:
            with self._lock:
                task = self._pop_ready()
                if task is not None:
                    return task

            if block_timeout is None or time.time() >= deadline:
                return None
            time.sleep(0.05)

    def peek(self) -> Optional[PriorityTask]:
        """Return the top task without removing it."""
        with self._lock:
            return self._heap[0] if self._heap else None

    def remove(self, task_id: str) -> bool:
        """Remove a specific task by ID.

        Returns ``True`` if found and removed.
        """
        with self._lock:
            for i, task in enumerate(self._heap):
                if task.task_id == task_id:
                    self._heap.pop(i)
                    heapq.heapify(self._heap)
                    logger.debug("PriorityQueue: removed task_id=%s", task_id)
                    return True
            return False

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Current number of tasks in the queue."""
        with self._lock:
            return len(self._heap)

    @property
    def is_empty(self) -> bool:
        return self.size() == 0

    def inspect(self) -> List[dict]:
        """Return a snapshot of all tasks as dicts."""
        with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "priority": t.priority,
                    "priority_label": self._priority_label(t.priority),
                    "ready": t.is_ready,
                    "ready_at": t.ready_at,
                    "created_at": t.created_at,
                }
                for t in sorted(self._heap)
            ]

    def ready_count(self) -> int:
        """Number of tasks that are currently ready to run."""
        now = time.time()
        with self._lock:
            return sum(1 for t in self._heap if t.ready_at <= now)

    def __len__(self) -> int:
        return self.size()

    def __iter__(self) -> Iterator[PriorityTask]:
        """Iterate (snapshot) ordered tasks."""
        with self._lock:
            return iter(sorted(self._heap))

    def __repr__(self) -> str:
        return f"PriorityTaskQueue(size={self.size()} max={self.max_size})"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pop_ready(self) -> Optional[PriorityTask]:
        """Internal: pop and return the top task if ready. Caller holds lock."""
        if not self._heap:
            return None
        top = self._heap[0]
        if not top.is_ready:
            return None
        return heapq.heappop(self._heap)

    @staticmethod
    def _priority_label(value: int) -> str:
        for level in Priority:
            if value <= level:
                return level.name
        return "IDLE"
