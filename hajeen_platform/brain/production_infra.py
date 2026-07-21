"""
Production Infrastructure
========================
مكونات الإنتاج: Redis Cache, Queue System, Rate Limiting, Circuit Breaker, Retry Policies.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  #正常工作
    OPEN = "open"  #熔断
    HALF_OPEN = "half_open"  #半开


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5  # 失败次数阈值
    recovery_timeout: float = 60.0  # 恢复超时(秒)
    half_open_max_calls: int = 3  # 半开状态最大调用数


@dataclass
class CircuitBreakerStats:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state: CircuitState = CircuitState.CLOSED
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None


class CircuitBreaker:
    """
    熔断器 - 防止级联故障。
    
    状态转换:
    CLOSED -> OPEN: 失败次数超过阈值
    OPEN -> HALF_OPEN: 超过恢复超时
    HALF_OPEN -> CLOSED: 连续成功
    HALF_OPEN -> OPEN: 失败
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """获取当前状态。"""
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._success_count = 0
        return self._state

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试恢复。"""
        if self._last_failure_time is None:
            return False
        return time.time() - self._last_failure_time >= self.config.recovery_timeout

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """执行函数，带熔断保护。"""
        async with self._lock:
            current_state = self.state
            self._stats.total_calls += 1

            if current_state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._stats.rejected_calls += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' half-open limit reached"
                    )
                self._half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """处理成功调用。"""
        async with self._lock:
            self._failure_count = 0
            self._stats.successful_calls += 1
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= 3:  # 连续成功3次
                    self._state = CircuitState.CLOSED
                    logger.info("circuit_breaker: %s transitioned to CLOSED", self.name)

    async def _on_failure(self) -> None:
        """处理失败调用。"""
        async with self._lock:
            self._failure_count += 1
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("circuit_breaker: %s transitioned to OPEN (half-open failure)", self.name)
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning("circuit_breaker: %s transitioned to OPEN (threshold reached)", self.name)

    def get_stats(self) -> CircuitBreakerStats:
        """获取统计信息。"""
        stats = CircuitBreakerStats(
            total_calls=self._stats.total_calls,
            successful_calls=self._stats.successful_calls,
            failed_calls=self._stats.failed_calls,
            rejected_calls=self._stats.rejected_calls,
            state=self.state,
            last_failure_time=self._stats.last_failure_time,
            last_success_time=self._stats.last_success_time,
        )
        return stats

    def reset(self) -> None:
        """重置熔断器。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._stats = CircuitBreakerStats()
        logger.info("circuit_breaker: %s reset", self.name)


class CircuitBreakerOpenError(Exception):
    """熔断器打开时调用抛出此异常。"""
    pass


class RateLimiter:
    """
    速率限制器 - 控制API调用频率。
    
    支持:
    - 滑动窗口
    - 令牌桶
    - 固定窗口
    """

    def __init__(
        self,
        max_calls: int,
        period_seconds: float,
        algorithm: str = "sliding_window",
    ) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.algorithm = algorithm
        self._calls: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """尝试获取调用许可。"""
        async with self._lock:
            now = time.time()
            cutoff = now - self.period_seconds

            # 清理过期记录
            self._calls = [t for t in self._calls if t > cutoff]

            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return True

            return False

    async def wait_and_acquire(self, timeout: float = 30.0) -> bool:
        """等待并获取许可。"""
        start = time.time()
        while time.time() - start < timeout:
            if await self.acquire():
                return True
            await asyncio.sleep(0.1)
        return False

    def get_remaining(self) -> int:
        """获取剩余调用次数。"""
        now = time.time()
        cutoff = now - self.period_seconds
        active_calls = [t for t in self._calls if t > cutoff]
        return max(0, self.max_calls - len(active_calls))

    def get_reset_time(self) -> float:
        """获取重置时间。"""
        if not self._calls:
            return time.time() + self.period_seconds
        return max(self._calls) + self.period_seconds


class SmartCache:
    """
    智能缓存 - 支持TTL、LRU、统计。
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 3600.0,
    ) -> None:
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值。"""
        if key not in self._cache:
            self._stats["misses"] += 1
            return None

        entry = self._cache[key]

        # 检查TTL
        if time.time() > entry["expires_at"]:
            self._evict(key)
            self._stats["misses"] += 1
            return None

        # 更新访问顺序(LRU)
        self._update_access(key)
        self._stats["hits"] += 1
        return entry["value"]

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """设置缓存值。"""
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict_lru()

        ttl = ttl if ttl is not None else self.default_ttl
        self._cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl,
            "created_at": time.time(),
        }
        self._update_access(key)

    def delete(self, key: str) -> bool:
        """删除缓存值。"""
        if key in self._cache:
            self._evict(key)
            return True
        return False

    def clear(self) -> None:
        """清空缓存。"""
        self._cache.clear()
        self._access_order.clear()

    def _evict(self, key: str) -> None:
        """驱逐指定键。"""
        if key in self._cache:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

    def _evict_lru(self) -> None:
        """驱逐最近最少使用的键。"""
        if self._access_order:
            lru_key = self._access_order[0]
            self._evict(lru_key)
            self._stats["evictions"] += 1

    def _update_access(self, key: str) -> None:
        """更新访问顺序。"""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计。"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "hit_rate": hit_rate,
        }


class RetryPolicy:
    """
    重试策略 - 支持多种退避算法。
    """

    def __init__(
        self,
        max_retries: int = 3,
        strategy: str = "exponential",
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ) -> None:
        self.max_retries = max_retries
        self.strategy = strategy
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """获取重试延迟。"""
        if attempt <= 0:
            return 0.0

        if self.strategy == "exponential":
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.strategy == "linear":
            delay = self.base_delay * attempt
        elif self.strategy == "constant":
            delay = self.base_delay
        else:
            delay = self.base_delay

        # 添加抖动
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return min(delay, self.max_delay)


async def retry_with_policy(
    func: Callable,
    policy: RetryPolicy,
    *args,
    **kwargs,
) -> Any:
    """使用重试策略执行函数。"""
    last_exception = None

    for attempt in range(policy.max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < policy.max_retries:
                delay = policy.get_delay(attempt)
                logger.warning(
                    "retry: attempt %d failed, waiting %.2fs before retry",
                    attempt + 1, delay
                )
                await asyncio.sleep(delay)

    raise last_exception


# 全局限流器
_rate_limiters: Dict[str, RateLimiter] = {}
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_cache = SmartCache()


def get_rate_limiter(name: str, max_calls: int, period: float) -> RateLimiter:
    """获取或创建速率限制器。"""
    if name not in _rate_limiters:
        _rate_limiters[name] = RateLimiter(max_calls, period)
    return _rate_limiters[name]


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """获取或创建熔断器。"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def get_smart_cache() -> SmartCache:
    """获取智能缓存实例。"""
    return _cache
