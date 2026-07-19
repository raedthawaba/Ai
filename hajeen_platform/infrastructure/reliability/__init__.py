"""
Reliability Layer
================

Provides fault-tolerance patterns:
- Circuit Breaker
- Retry Policies
- Timeout Management
- Rate Limiting
- Backpressure
- Graceful Shutdown

Usage:
    # Circuit breaker
    with circuit_breaker("api"):
        await call_api()
    
    # Retry with backoff
    await retry(max_attempts=3, backoff="exponential")(my_function)()
    
    # Timeout
    await timeout(5)(my_function)()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import (
    Any, Callable, Dict, List, Optional, 
    TypeVar, Union, Awaitable, Tuple
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading
import random

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern implementation.
    
    Prevents cascading failures by failing fast when a service is down.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service is failing, requests are rejected
    - HALF_OPEN: Testing if service has recovered
    """
    
    name: str
    failure_threshold: int = 5        # Failures before opening
    success_threshold: int = 3        # Successes before closing
    timeout: float = 60               # Seconds before half-open
    expected_exception: type = Exception
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                if time.time() - self._last_failure_time >= self.timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state
    
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED
    
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN
    
    def is_half_open(self) -> bool:
        return self.state == CircuitState.HALF_OPEN
    
    def record_success(self):
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    logger.info(f"Circuit {self.name}: Closing after {self._success_count} successes")
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            else:
                self._failure_count = 0
    
    def record_failure(self):
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit {self.name}: Opening after failure in half-open")
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._failure_count >= self.failure_threshold:
                logger.warning(f"Circuit {self.name}: Opening after {self._failure_count} failures")
                self._state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        return self.state != CircuitState.OPEN
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with circuit breaker protection."""
        if not self.can_execute():
            raise CircuitOpenError(f"Circuit {self.name} is open")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self.record_success()
            return result
            
        except self.expected_exception as e:
            self.record_failure()
            raise
        except Exception as e:
            self.record_failure()
            raise
    
    def reset(self):
        """Reset circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "failure_threshold": self.failure_threshold,
                "timeout": self.timeout
            }


class CircuitOpenError(Exception):
    """Raised when circuit is open."""
    pass


class CircuitBreakerRegistry:
    """Registry for circuit breakers."""
    
    _breakers: Dict[str, CircuitBreaker] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get(cls, name: str, **kwargs) -> CircuitBreaker:
        """Get or create circuit breaker."""
        with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(name=name, **kwargs)
            return cls._breakers[name]
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict]:
        """Get stats for all circuit breakers."""
        return {name: cb.get_stats() for name, cb in cls._breakers.items()}


def circuit_breaker(name: str, **kwargs):
    """
    Decorator for circuit breaker protection.
    
    Usage:
        @circuit_breaker("api", failure_threshold=3)
        async def call_api():
            ...
    """
    breaker = CircuitBreakerRegistry.get(name, **kwargs)
    
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            return await breaker.execute(func, *args, **kwargs)
        
        wrapper.breaker = breaker
        return wrapper
    
    return decorator


# =============================================================================
# RETRY POLICIES
# =============================================================================

class BackoffStrategy(Enum):
    """Backoff strategies."""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


@dataclass
class RetryPolicy:
    """
    Retry policy with configurable backoff.
    
    Usage:
        @retry(max_attempts=3, backoff="exponential", base_delay=1)
        async def my_function():
            ...
    """
    
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    jitter: float = 0.1  # Random jitter factor
    retriable_exceptions: Tuple[type, ...] = (Exception,)
    on_retry: Optional[Callable[[Exception, int], None]] = None
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for attempt."""
        if self.backoff == BackoffStrategy.FIXED:
            delay = self.base_delay
        elif self.backoff == BackoffStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.backoff == BackoffStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (attempt - 1))
        else:  # EXPONENTIAL_JITTER
            delay = self.base_delay * (2 ** (attempt - 1))
            delay *= (1 + random.uniform(-self.jitter, self.jitter))
        
        return min(delay, self.max_delay)
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if should retry."""
        if attempt >= self.max_attempts:
            return False
        
        return isinstance(exception, self.retriable_exceptions)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff: Union[str, BackoffStrategy] = "exponential",
    jitter: float = 0.1,
    retriable: Tuple[type, ...] = (Exception,)
):
    """
    Decorator for automatic retry with backoff.
    
    Usage:
        @retry(max_attempts=3, backoff="exponential")
        async def my_function():
            ...
    """
    if isinstance(backoff, str):
        backoff = BackoffStrategy(backoff)
    
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        backoff=backoff,
        jitter=jitter,
        retriable_exceptions=retriable
    )
    
    def decorator(func: Callable):
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except policy.retriable_exceptions as e:
                    last_exception = e
                    
                    if not policy.should_retry(e, attempt):
                        raise
                    
                    delay = policy.calculate_delay(attempt)
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s: {e}"
                    )
                    
                    if policy.on_retry:
                        policy.on_retry(e, attempt)
                    
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except policy.retriable_exceptions as e:
                    last_exception = e
                    
                    if not policy.should_retry(e, attempt):
                        raise
                    
                    delay = policy.calculate_delay(attempt)
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
            
            raise last_exception
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# =============================================================================
# RATE LIMITING
# =============================================================================

@dataclass
class RateLimiter:
    """
    Token bucket rate limiter.
    
    Usage:
        limiter = RateLimiter(rate=100, per=60)  # 100 per minute
        
        @limiter
        async def my_function():
            ...
    """
    
    rate: float          # Tokens per period
    per: float = 60.0  # Period in seconds
    burst: Optional[float] = None  # Max burst capacity
    
    _tokens: float = field(init=False)
    _last_update: float = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    
    def __post_init__(self):
        self._tokens = self.burst or self.rate
        self._last_update = time.time()
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update
        
        # Add tokens
        tokens_to_add = elapsed * (self.rate / self.per)
        self._tokens = min(self.burst or self.rate, self._tokens + tokens_to_add)
        self._last_update = now
    
    async def acquire(self, tokens: float = 1, timeout: float = 30) -> bool:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            timeout: Max time to wait
            
        Returns:
            True if acquired, False if timeout
        """
        start = time.time()
        
        while True:
            with self._lock:
                self._refill()
                
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
            
            if time.time() - start >= timeout:
                return False
            
            await asyncio.sleep(0.01)
    
    def try_acquire(self, tokens: float = 1) -> bool:
        """Try to acquire tokens without waiting."""
        with self._lock:
            self._refill()
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


def rate_limit(rate: float, per: float = 60, burst: Optional[float] = None):
    """
    Decorator for rate limiting.
    
    Usage:
        @rate_limit(100, per=60)
        async def my_function():
            ...
    """
    limiter = RateLimiter(rate=rate, per=per, burst=burst)
    
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            if not await limiter.acquire():
                raise RateLimitExceeded(f"Rate limit exceeded: {rate}/{per}")
            return await func(*args, **kwargs)
        
        wrapper.limiter = limiter
        return wrapper
    
    return decorator


# =============================================================================
# TIMEOUT
# =============================================================================

async def timeout(seconds: float):
    """
    Decorator for function timeout.
    
    Usage:
        @timeout(5)
        async def my_function():
            ...
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=seconds
            )
        return wrapper
    return decorator


# =============================================================================
# GRACEFUL SHUTDOWN
# =============================================================================

class GracefulShutdown:
    """
    Graceful shutdown handler.
    
    Coordinates shutdown of services, waiting for in-flight requests.
    """
    
    def __init__(self, timeout: float = 30):
        self.timeout = timeout
        self._shutdown = False
        self._tasks: List[asyncio.Task] = []
        self._callbacks: List[Callable] = []
        self._lock = threading.Lock()
    
    def register_callback(self, callback: Callable):
        """Register a shutdown callback."""
        self._callbacks.append(callback)
    
    def add_task(self, task: asyncio.Task):
        """Add a task to wait for."""
        with self._lock:
            self._tasks.append(task)
    
    async def shutdown(self):
        """Perform graceful shutdown."""
        logger.info("Starting graceful shutdown...")
        self._shutdown = True
        
        # Callbacks
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Shutdown callback error: {e}")
        
        # Wait for tasks
        if self._tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for tasks during shutdown")
        
        logger.info("Graceful shutdown complete")
    
    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown


# =============================================================================
# BACKPRESSURE
# =============================================================================

class BackpressureLimiter:
    """
    Backpressure limiter to prevent system overload.
    
    Limits concurrent operations and queues excess.
    """
    
    def __init__(
        self,
        max_concurrent: int = 100,
        max_queue: int = 1000
    ):
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        
        self._semaphore: asyncio.Semaphore = field(init=False)
        self._queue: asyncio.Queue = field(init=False)
        self._active_count = 0
        self._lock = threading.Lock()
    
    def __post_init__(self):
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._queue = asyncio.Queue(maxsize=self.max_queue)
    
    async def __aenter__(self):
        """Acquire backpressure token."""
        await self._semaphore.acquire()
        with self._lock:
            self._active_count += 1
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release backpressure token."""
        with self._lock:
            self._active_count -= 1
        self._semaphore.release()
    
    @property
    def active_count(self) -> int:
        return self._active_count
    
    @property
    def queue_size(self) -> int:
        return self._queue.qsize()
    
    def is_overloaded(self) -> bool:
        return self._active_count >= self.max_concurrent


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

# Global circuit breaker registry
circuit_breakers = CircuitBreakerRegistry

# Global graceful shutdown
shutdown_handler = GracefulShutdown()
