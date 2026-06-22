"""
Retry Manager — handles task retry logic with exponential backoff,
jitter, dead-letter queue routing, and circuit breaking.
"""
from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class RetryStrategy(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"
    FIBONACCI = "fibonacci"


@dataclass
class RetryPolicy:
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0
    max_delay: float = 300.0
    jitter: bool = True
    jitter_range: float = 0.25
    retryable_exceptions: List[Type[Exception]] = field(default_factory=list)
    non_retryable_exceptions: List[Type[Exception]] = field(default_factory=list)

    def compute_delay(self, attempt: int) -> float:
        if self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.strategy == RetryStrategy.FIBONACCI:
            a, b = 1, 1
            for _ in range(attempt - 1):
                a, b = b, a + b
            delay = self.base_delay * a
        else:
            delay = self.base_delay

        delay = min(delay, self.max_delay)

        if self.jitter:
            jitter_amount = delay * self.jitter_range
            delay = delay + random.uniform(-jitter_amount, jitter_amount)

        return max(0.0, delay)

    def should_retry(self, exc: Exception, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False

        for exc_type in self.non_retryable_exceptions:
            if isinstance(exc, exc_type):
                return False

        if self.retryable_exceptions:
            return any(isinstance(exc, exc_type) for exc_type in self.retryable_exceptions)

        return True


class CircuitBreaker:
    """Circuit breaker to stop retrying when a service is clearly down."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time > self.reset_timeout:
                self._state = self.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def call_succeeded(self) -> None:
        self._failure_count = 0
        self._state = self.CLOSED

    def call_failed(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == self.HALF_OPEN:
            self._state = self.OPEN
        elif self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning("Circuit breaker opened after %d failures", self._failure_count)

    def is_open(self) -> bool:
        return self.state == self.OPEN


class RetryManager:
    """Manages task retries with configurable policies and circuit breaking."""

    DEFAULT_POLICY = RetryPolicy(max_retries=3, strategy=RetryStrategy.EXPONENTIAL)

    TASK_POLICIES: Dict[str, RetryPolicy] = {
        "inference": RetryPolicy(
            max_retries=2,
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=5.0,
            max_delay=60.0,
        ),
        "training": RetryPolicy(
            max_retries=1,
            strategy=RetryStrategy.FIXED,
            base_delay=300.0,
        ),
        "data": RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=2.0,
            max_delay=600.0,
        ),
        "embedding": RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
        ),
    }

    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def get_policy(self, task_name: str) -> RetryPolicy:
        for prefix, policy in self.TASK_POLICIES.items():
            if task_name.startswith(prefix):
                return policy
        return self.DEFAULT_POLICY

    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        if service_name not in self._circuit_breakers:
            self._circuit_breakers[service_name] = CircuitBreaker()
        return self._circuit_breakers[service_name]

    def execute_with_retry(
        self,
        func: Callable,
        task_name: str,
        task_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        policy = self.get_policy(task_name)
        cb = self.get_circuit_breaker(task_name.split(".")[0])
        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt <= policy.max_retries:
            if cb.is_open():
                raise RuntimeError(
                    f"Circuit breaker open for {task_name} — service unavailable"
                )

            try:
                result = func(*args, **kwargs)
                cb.call_succeeded()
                self._record_success(task_id, task_name, attempt)
                return result

            except Exception as exc:
                last_exc = exc
                cb.call_failed()
                attempt += 1

                if not policy.should_retry(exc, attempt):
                    logger.error(
                        "Task %s failed permanently after %d attempts: %s",
                        task_id, attempt, exc,
                    )
                    self._send_to_dead_letter(task_id, task_name, exc)
                    raise

                delay = policy.compute_delay(attempt)
                logger.warning(
                    "Task %s attempt %d/%d failed: %s — retrying in %.1fs",
                    task_id, attempt, policy.max_retries, exc, delay,
                )
                time.sleep(delay)

        if last_exc:
            self._send_to_dead_letter(task_id, task_name, last_exc)
            raise last_exc

    def _record_success(self, task_id: str, task_name: str, attempts: int) -> None:
        key = f"task_stats:{task_name}:success"
        self.redis.incr(key)
        if attempts > 0:
            retry_key = f"task_stats:{task_name}:retried"
            self.redis.incr(retry_key)

    def _send_to_dead_letter(
        self, task_id: str, task_name: str, exc: Exception
    ) -> None:
        import json
        payload = json.dumps({
            "task_id": task_id,
            "task_name": task_name,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "timestamp": time.time(),
        })
        self.redis.lpush("dead_letter_queue", payload)
        self.redis.incr(f"task_stats:{task_name}:dead_letter")
        logger.error("Task %s sent to dead letter queue", task_id)
