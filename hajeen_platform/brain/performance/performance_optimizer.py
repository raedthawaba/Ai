"""
Performance Optimization Module
==============================
Phase 17: Performance Optimization
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class ParallelReasoningEngine:
    """Parallel reasoning with concurrency control."""
    
    def __init__(self, max_parallel: int = 4):
        self.max_parallel = max_parallel
        self._semaphore = asyncio.Semaphore(max_parallel)
    
    async def reason_parallel(self, tasks: List[Callable], args_list: List = None) -> List[Any]:
        args_list = args_list or [() for _ in tasks]
        
        async def bounded_task(task, args):
            async with self._semaphore:
                if asyncio.iscoroutinefunction(task):
                    return await task(*args)
                return task(*args)
        
        coroutines = [bounded_task(t, a) for t, a in zip(tasks, args_list)]
        return await asyncio.gather(*coroutines, return_exceptions=True)


class SmartCache:
    """Intelligent caching with TTL and LRU."""
    
    def __init__(self, max_size: int = 10000, default_ttl: float = 3600.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        self._hits = 0
        self._misses = 0
    
    async def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry["value"]
        self._misses += 1
        return None
    
    async def set(self, key: str, value: Any, ttl: float = None):
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict()
        self._cache[key] = {
            "value": value,
            "expires_at": time.time() + (ttl or self.default_ttl),
        }
        if key not in self._access_order:
            self._access_order.append(key)
    
    def _evict(self):
        if self._access_order:
            key = self._access_order.pop(0)
            self._cache.pop(key, None)
    
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hit_rate": self._hits / total if total > 0 else 0,
        }


class BatchProcessor:
    """Batch processing for throughput."""
    
    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self._pending: List[Any] = []
    
    async def add(self, item: Any, processor: Callable) -> Any:
        self._pending.append(item)
        if len(self._pending) >= self.batch_size:
            return await self._process(processor)
        return None
    
    async def flush(self, processor: Callable) -> List[Any]:
        if self._pending:
            return await self._process(processor)
        return []
    
    async def _process(self, processor: Callable) -> List[Any]:
        items = self._pending
        self._pending = []
        return [processor(item) for item in items]


class StreamingReasoning:
    """Streaming reasoning for large problems."""
    
    def __init__(self, chunk_size: int = 1000):
        self.chunk_size = chunk_size
    
    async def reason(self, problem: str, processor: Callable) -> List[Any]:
        words = problem.split()
        chunks = [" ".join(words[i:i+self.chunk_size]) for i in range(0, len(words), self.chunk_size)]
        
        results = []
        for chunk in chunks:
            if asyncio.iscoroutinefunction(processor):
                result = await processor(chunk)
            else:
                result = processor(chunk)
            results.append(result)
        
        return results


class IncrementalReasoning:
    """Incremental reasoning with state tracking."""
    
    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._history: List[Dict] = []
    
    async def step(self, name: str, func: Callable, *args, **kwargs) -> Any:
        context = {"state": self._state, "history": self._history}
        
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs, context=context)
        else:
            result = func(*args, **kwargs, context=context)
        
        self._state[name] = result
        self._history.append({"step": name, "result": result})
        
        return result
    
    def get_state(self) -> Dict[str, Any]:
        return self._state.copy()


class PerformanceOptimizer:
    """Main performance optimizer."""
    
    def __init__(self):
        self.parallel = ParallelReasoningEngine()
        self.cache = SmartCache()
        self.batch = BatchProcessor()
        self.streaming = StreamingReasoning()
        self.incremental = IncrementalReasoning()
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "cache": self.cache.stats(),
        }


_optimizer: Optional[PerformanceOptimizer] = None


def get_performance_optimizer() -> PerformanceOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = PerformanceOptimizer()
    return _optimizer
