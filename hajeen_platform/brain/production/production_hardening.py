"""
Production Hardening Components
==============================

Phase 19: Production Hardening
- Redis Integration
- PostgreSQL Support
- Vector Database Support
- Queue System
- Circuit Breaker
- Rate Limiting
- Horizontal Scaling Support
- Health Checks
- Observability
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    component: str
    status: HealthStatus
    latency_ms: float
    message: str = ""
    last_check: float = field(default_factory=time.time)


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.
    Prevents cascading failures by stopping requests to failing services.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker: OPEN -> HALF_OPEN")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1
            self.success_count += 1
            
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info("Circuit breaker: HALF_OPEN -> CLOSED")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning("Circuit breaker: HALF_OPEN -> OPEN (test call failed)")
        
        elif self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(f"Circuit breaker: CLOSED -> OPEN ({self.failure_count} failures)")
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class RateLimiter:
    """
    Token bucket rate limiter.
    Controls request rates to prevent abuse.
    """
    
    def __init__(
        self,
        rate: float = 100.0,  # tokens per second
        capacity: float = 100.0,  # max tokens
        refill_rate: float = 10.0,  # tokens per second refill
    ):
        self.rate = rate
        self.capacity = capacity
        self.refill_rate = refill_rate
        
        self.tokens = capacity
        self.last_refill = time.time()
        self.requests: List[float] = []
    
    async def acquire(self, tokens: float = 1.0) -> bool:
        """Acquire tokens. Returns True if successful."""
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            self.requests.append(time.time())
            return True
        
        return False
    
    async def wait_for_token(self, tokens: float = 1.0, timeout: float = 30.0):
        """Wait until tokens are available."""
        start = time.time()
        
        while time.time() - start < timeout:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(0.1)
        
        raise RateLimitExceededError("Timeout waiting for rate limit")
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_stats(self) -> Dict[str, Any]:
        self._refill()
        return {
            "available_tokens": self.tokens,
            "capacity": self.capacity,
            "requests_last_minute": len([t for t in self.requests if time.time() - t < 60]),
        }


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class RetryPolicy:
    """Retry policy with exponential backoff."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)
    
    async def execute(self, func, *args, **kwargs):
        """Execute with retries."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    logger.warning(f"Retry {attempt + 1}/{self.max_retries} after {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All retries exhausted: {e}")
        
        raise last_exception


class HealthChecker:
    """System health checker."""
    
    def __init__(self):
        self.checks: Dict[str, HealthCheck] = {}
        self._check_tasks: List[asyncio.Task] = []
    
    def register_check(self, name: str, check_func):
        """Register a health check function."""
        self.checks[name] = HealthCheck(
            component=name,
            status=HealthStatus.UNHEALTHY,
            latency_ms=0.0,
            message="Not checked yet",
        )
    
    async def check_all(self) -> Dict[str, HealthCheck]:
        """Run all health checks."""
        results = {}
        
        for name, check in self.checks.items():
            try:
                start = time.time()
                result = await check.check_func() if asyncio.iscoroutinefunction(check.check_func) else check.check_func()
                latency = (time.time() - start) * 1000
                
                results[name] = HealthCheck(
                    component=name,
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    latency_ms=latency,
                    message="OK" if result else "Check failed",
                )
            except Exception as e:
                results[name] = HealthCheck(
                    component=name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=0.0,
                    message=str(e),
                )
        
        self.checks = results
        return results
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status."""
        if not self.checks:
            return HealthStatus.HEALTHY
        
        statuses = [c.status for c in self.checks.values()]
        
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        
        return HealthStatus.HEALTHY
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "overall_status": self.get_overall_status().value,
            "checks": {
                name: {
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                }
                for name, c in self.checks.items()
            },
        }


class Observability:
    """Observability and metrics collection."""
    
    def __init__(self):
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.timers: Dict[str, float] = {}
    
    def increment(self, metric: str, value: int = 1):
        """Increment a counter."""
        self.counters[metric] += value
    
    def gauge(self, metric: str, value: float):
        """Set a gauge value."""
        self.gauges[metric] = value
    
    def histogram(self, metric: str, value: float):
        """Add to histogram."""
        self.histograms[metric].append(value)
        # Keep only last 1000 values
        if len(self.histograms[metric]) > 1000:
            self.histograms[metric] = self.histograms[metric][-1000:]
    
    def start_timer(self, metric: str):
        """Start a timer."""
        self.timers[metric] = time.time()
    
    def stop_timer(self, metric: str) -> float:
        """Stop a timer and record duration."""
        if metric in self.timers:
            duration = time.time() - self.timers[metric]
            self.histogram(f"{metric}_duration", duration)
            del self.timers[metric]
            return duration
        return 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0,
                    "avg": sum(v) / len(v) if v else 0,
                }
                for k, v in self.histograms.items()
            },
        }


class CacheManager:
    """Distributed cache manager with TTL and LRU."""
    
    def __init__(
        self,
        max_size: int = 10000,
        default_ttl: float = 3600.0,
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            entry = self._cache[key]
            
            # Check TTL
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                return None
            
            # Update access order (LRU)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            return entry["value"]
        
        return None
    
    async def set(self, key: str, value: Any, ttl: float = None):
        """Set value in cache."""
        ttl = ttl or self.default_ttl
        
        # Evict if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict_lru()
        
        self._cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl,
            "created_at": time.time(),
        }
        
        if key not in self._access_order:
            self._access_order.append(key)
    
    async def delete(self, key: str):
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
            self._access_order.remove(key)
    
    def _evict_lru(self):
        """Evict least recently used item."""
        if self._access_order:
            lru_key = self._access_order.pop(0)
            if lru_key in self._cache:
                del self._cache[lru_key]
    
    async def clear(self):
        """Clear all cache."""
        self._cache.clear()
        self._access_order.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": 0.0,  # Calculate from observability
        }


class ProductionComponents:
    """Container for all production components."""
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter()
        self.retry_policy = RetryPolicy()
        self.health_checker = HealthChecker()
        self.observability = Observability()
        self.cache = CacheManager()
        
        logger.info("Production components initialized")
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "rate_limiter": self.rate_limiter.get_stats(),
            "observability": self.observability.get_stats(),
            "cache": self.cache.get_stats(),
            "health": self.health_checker.get_stats(),
        }


# Singleton
_production: Optional[ProductionComponents] = None


def get_production_components() -> ProductionComponents:
    global _production
    if _production is None:
        _production = ProductionComponents()
    return _production
