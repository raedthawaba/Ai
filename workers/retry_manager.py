"""Retry Manager — section 6.8.

Handles retry logic with exponential backoff for tasks.

Features:
- Configurable retry limits
- Exponential backoff with optional jitter
- Per-task retry state tracking
- Dead task detection
"""
from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetryStatus(str, Enum):
    PENDING  = "pending"
    RETRYING = "retrying"
    FAILED   = "failed"
    DEAD     = "dead"
    SUCCESS  = "success"


@dataclass
class RetryState:
    """Tracks retry history for a single task."""

    task_id: str
    task_name: str
    attempts: int = 0
    max_attempts: int = 3
    status: RetryStatus = RetryStatus.PENDING
    last_error: Optional[str] = None
    last_attempt_at: float = field(default_factory=time.time)
    next_retry_at: float = field(default_factory=time.time)
    errors: List[str] = field(default_factory=list)

    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    @property
    def is_dead(self) -> bool:
        return self.status == RetryStatus.DEAD

    def record_attempt(self, error: Optional[str] = None) -> None:
        self.attempts += 1
        self.last_attempt_at = time.time()
        if error:
            self.last_error = error
            self.errors.append(error)
        self.status = RetryStatus.RETRYING if not self.is_exhausted else RetryStatus.DEAD

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "status": self.status.value,
            "last_error": self.last_error,
            "last_attempt_at": self.last_attempt_at,
            "next_retry_at": self.next_retry_at,
        }


@dataclass
class RetryConfig:
    """Configuration for exponential backoff."""

    max_attempts: int = 3
    initial_delay: float = 1.0    # seconds
    max_delay: float = 300.0      # 5 minutes cap
    backoff_factor: float = 2.0
    jitter: bool = True           # add ±25% random jitter


class RetryManager:
    """Manages retry state and backoff computation.

    Parameters
    ----------
    config:
        :class:`RetryConfig`.
    """

    def __init__(self, config: Optional[RetryConfig] = None) -> None:
        self.config = config or RetryConfig()
        self._states: Dict[str, RetryState] = {}

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def register(self, task_id: str, task_name: str) -> RetryState:
        """Register a new task for retry tracking."""
        state = RetryState(
            task_id=task_id,
            task_name=task_name,
            max_attempts=self.config.max_attempts,
        )
        self._states[task_id] = state
        logger.debug("RetryManager: registered task_id=%s name=%s", task_id, task_name)
        return state

    def get_state(self, task_id: str) -> Optional[RetryState]:
        return self._states.get(task_id)

    def record_failure(self, task_id: str, error: str) -> RetryState:
        """Record a task failure and compute the next retry delay.

        Parameters
        ----------
        task_id:
            Task identifier.
        error:
            Error message.

        Returns
        -------
        Updated :class:`RetryState`.
        """
        state = self._states.get(task_id)
        if state is None:
            state = RetryState(
                task_id=task_id, task_name="unknown",
                max_attempts=self.config.max_attempts,
            )
            self._states[task_id] = state

        state.record_attempt(error)
        delay = self.compute_delay(state.attempts)
        state.next_retry_at = time.time() + delay

        if state.is_exhausted:
            state.status = RetryStatus.DEAD
            logger.error(
                "RetryManager: task DEAD id=%s after %d attempts",
                task_id, state.attempts,
            )
        else:
            logger.warning(
                "RetryManager: task RETRY id=%s attempt=%d/%d delay=%.1fs",
                task_id, state.attempts, state.max_attempts, delay,
            )
        return state

    def record_success(self, task_id: str) -> Optional[RetryState]:
        """Mark a task as succeeded."""
        state = self._states.get(task_id)
        if state:
            state.status = RetryStatus.SUCCESS
        return state

    def should_retry(self, task_id: str) -> bool:
        """Return True when the task should be retried."""
        state = self._states.get(task_id)
        if state is None:
            return True  # unknown — allow first attempt
        return not state.is_exhausted and not state.is_dead

    def compute_delay(self, attempt: int) -> float:
        """Compute exponential backoff delay for ``attempt``.

        Parameters
        ----------
        attempt:
            Number of attempts already made (1-indexed).

        Returns
        -------
        Delay in seconds.
        """
        cfg = self.config
        delay = min(cfg.initial_delay * (cfg.backoff_factor ** (attempt - 1)), cfg.max_delay)
        if cfg.jitter:
            delay *= random.uniform(0.75, 1.25)
        return round(delay, 2)

    def dead_tasks(self) -> List[RetryState]:
        """Return all tasks that have exhausted their retries."""
        return [s for s in self._states.values() if s.is_dead]

    def summary(self) -> Dict[str, Any]:
        total = len(self._states)
        dead = sum(1 for s in self._states.values() if s.is_dead)
        retrying = sum(1 for s in self._states.values() if s.status == RetryStatus.RETRYING)
        success = sum(1 for s in self._states.values() if s.status == RetryStatus.SUCCESS)
        return {
            "total": total,
            "retrying": retrying,
            "dead": dead,
            "success": success,
        }

    def clear_completed(self) -> int:
        """Remove completed (success or dead) tasks from tracking."""
        to_remove = [
            tid for tid, s in self._states.items()
            if s.status in (RetryStatus.SUCCESS, RetryStatus.DEAD)
        ]
        for tid in to_remove:
            del self._states[tid]
        return len(to_remove)
