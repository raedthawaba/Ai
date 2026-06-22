"""Backpressure System — section 6.8.

Provides circuit-breaker and rate-limiting patterns to prevent
system overload when tasks fail repeatedly.

Features:
- Circuit breaker (CLOSED → OPEN → HALF_OPEN)
- Rate limiter (token bucket)
- Backpressure metrics
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED    = "closed"      # normal operation
    OPEN      = "open"        # failing — reject all
    HALF_OPEN = "half_open"   # testing recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5         # failures before OPEN
    recovery_timeout: float = 60.0     # seconds in OPEN before HALF_OPEN
    success_threshold: int = 2         # successes in HALF_OPEN before CLOSED


class CircuitBreaker:
    """Circuit breaker pattern for task protection.

    Parameters
    ----------
    name:
        Identifier for logging.
    config:
        :class:`CircuitBreakerConfig`.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float = 0.0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def allows_requests(self) -> bool:
        """Return True when the circuit allows a request through."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if time.time() - self._opened_at >= self.config.recovery_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                    return True
                return False
            # HALF_OPEN — allow one probe
            return True

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._transition(CircuitState.OPEN)

    def call(self, func: Callable, *args, **kwargs):
        """Execute ``func`` through the circuit breaker.

        Parameters
        ----------
        func:
            Callable to protect.

        Raises
        ------
        RuntimeError:
            When the circuit is open and rejecting requests.
        """
        if not self.allows_requests:
            raise RuntimeError(
                f"CircuitBreaker '{self.name}' is OPEN — requests rejected"
            )
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def status(self) -> Dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
        }

    def _transition(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        logger.info("CircuitBreaker '%s': %s → %s", self.name, old.value, new_state.value)


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token bucket rate limiter.

    Parameters
    ----------
    rate:
        Tokens added per second.
    capacity:
        Maximum token bucket size.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def acquire(self, tokens: float = 1.0, timeout: float = 0.0) -> bool:
        """Acquire tokens from the bucket.

        Parameters
        ----------
        tokens:
            Number of tokens to consume.
        timeout:
            Maximum seconds to wait.

        Returns
        -------
        True if acquired; False on timeout.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


# ---------------------------------------------------------------------------
# Backpressure Manager — combines breaker + limiter
# ---------------------------------------------------------------------------

class BackpressureManager:
    """Combines circuit breakers and rate limiters per queue.

    Parameters
    ----------
    default_rate:
        Default token refill rate (tasks/second).
    default_capacity:
        Default token bucket size.
    breaker_config:
        Default circuit breaker config.
    """

    def __init__(
        self,
        default_rate: float = 10.0,
        default_capacity: float = 20.0,
        breaker_config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._limiters: Dict[str, RateLimiter] = {}
        self._default_rate = default_rate
        self._default_capacity = default_capacity
        self._breaker_config = breaker_config or CircuitBreakerConfig()

    def get_breaker(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, self._breaker_config)
        return self._breakers[name]

    def get_limiter(self, name: str) -> RateLimiter:
        if name not in self._limiters:
            self._limiters[name] = RateLimiter(
                rate=self._default_rate, capacity=self._default_capacity
            )
        return self._limiters[name]

    def can_submit(self, queue: str) -> bool:
        """Return True when the queue's circuit is closed and there are tokens."""
        breaker = self.get_breaker(queue)
        limiter = self.get_limiter(queue)
        return breaker.allows_requests and limiter.available_tokens >= 1.0

    def acquire(self, queue: str) -> bool:
        """Acquire a token for the queue."""
        return self.get_limiter(queue).acquire(tokens=1.0, timeout=0.0)

    def status(self) -> Dict:
        return {
            "breakers": {name: b.status() for name, b in self._breakers.items()},
            "limiters": {
                name: {"available_tokens": round(l.available_tokens, 2)}
                for name, l in self._limiters.items()
            },
        }
