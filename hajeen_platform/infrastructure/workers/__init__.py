"""
Background Workers & Task Queue
==============================

Provides async task processing:
- Task Queue with priority
- Background workers
- Task scheduling
- Retry logic
- Progress tracking

Usage:
    # Define a task
    @task_queue.task()
    async def process_data(data):
        await do_work(data)
    
    # Enqueue task
    task_id = await task_queue.enqueue("process_data", {"key": "value"})
    
    # Get task status
    status = await task_queue.get_status(task_id)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import (
    Any, Callable, Dict, List, Optional, 
    TypeVar, Awaitable, Union
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import heapq
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(Enum):
    """Task priority."""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


@dataclass
class Task:
    """Task definition."""
    id: str
    name: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: Optional[float] = None  # seconds
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # Task IDs
    
    @property
    def is_done(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED, 
            TaskStatus.FAILED, 
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT
        )
    
    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


@dataclass
class ScheduledTask:
    """Scheduled task with run time."""
    run_at: float  # timestamp
    task: Task
    heap_index: int = -1
    
    def __lt__(self, other: ScheduledTask) -> bool:
        return self.run_at < other.run_at


class TaskQueue:
    """
    Async task queue with priority and scheduling.
    
    Features:
    - Priority-based execution
    - Scheduled execution
    - Retry with backoff
    - Task dependencies
    - Progress tracking
    - Worker pool
    """
    
    def __init__(
        self,
        max_workers: int = 10,
        default_timeout: float = 300,
        default_retries: int = 3
    ):
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._default_retries = default_retries
        
        # Task storage
        self._tasks: Dict[str, Task] = {}
        self._pending: List[Task] = []  # Priority queue
        self._scheduled: List[ScheduledTask] = []  # Scheduled tasks
        self._running: Dict[str, asyncio.Task] = {}
        
        # Workers
        self._worker_pool: Optional[ThreadPoolExecutor] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Lock
        self._lock = threading.Lock()
        
        # Callbacks
        self._on_complete: Dict[str, List[Callable]] = defaultdict(list)
        self._on_failure: Dict[str, List[Callable]] = defaultdict(list)
        
        # Stats
        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "running": 0
        }
        
        self._running_flag = False
    
    async def start(self):
        """Start the task queue."""
        self._running_flag = True
        self._loop = asyncio.get_event_loop()
        
        # Start worker loop
        self._worker_task = asyncio.create_task(self._worker_loop())
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info(f"Task queue started with {self._max_workers} workers")
    
    async def stop(self, timeout: float = 30):
        """Stop the task queue."""
        self._running_flag = False
        
        # Cancel pending tasks
        for task_id in list(self._running.keys()):
            await self.cancel(task_id)
        
        # Wait for workers
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout)
            except asyncio.TimeoutError:
                pass
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
        
        logger.info("Task queue stopped")
    
    def task(
        self,
        name: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        retries: int = 3,
        timeout: float = 300
    ):
        """
        Decorator to register a task.
        
        Usage:
            @task_queue.task(name="process", priority=TaskPriority.HIGH)
            async def process(data):
                ...
        """
        def decorator(func: Callable):
            task_name = name or func.__name__
            
            async def wrapper(*args, **kwargs):
                return await self.enqueue(
                    task_name,
                    *args,
                    func=func,
                    priority=priority,
                    retries=retries,
                    timeout=timeout,
                    **kwargs
                )
            
            # Attach metadata
            wrapper.task_name = task_name
            wrapper.task_func = func
            wrapper.is_task = True
            
            return wrapper
        
        return decorator
    
    async def enqueue(
        self,
        name: str,
        *args,
        func: Optional[Callable] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        retries: int = None,
        timeout: float = None,
        scheduled_at: Optional[datetime] = None,
        dependencies: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Enqueue a task.
        
        Args:
            name: Task name
            *args: Task arguments
            func: Task function (if not using registered task)
            priority: Task priority
            retries: Max retries
            timeout: Task timeout
            scheduled_at: Run at specific time
            dependencies: Task IDs this depends on
            
        Returns:
            Task ID
        """
        retries = retries if retries is not None else self._default_retries
        timeout = timeout if timeout is not None else self._default_timeout
        
        task = Task(
            id=str(uuid.uuid4()),
            name=name,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=retries,
            timeout=timeout,
            dependencies=dependencies or []
        )
        
        with self._lock:
            self._tasks[task.id] = task
            self._stats["submitted"] += 1
        
        # Handle scheduling
        if scheduled_at:
            scheduled_task = ScheduledTask(
                run_at=scheduled_at.timestamp(),
                task=task
            )
            heapq.heappush(self._scheduled, scheduled_task)
        else:
            # Check dependencies
            if not self._check_dependencies(task):
                # Requeue after checking dependencies
                asyncio.create_task(self._wait_for_dependencies(task))
            else:
                self._enqueue_task(task)
        
        logger.debug(f"Enqueued task {task.id}: {name}")
        return task.id
    
    def _enqueue_task(self, task: Task):
        """Add task to priority queue."""
        with self._lock:
            heapq.heappush(self._pending, task)
    
    def _check_dependencies(self, task: Task) -> bool:
        """Check if all dependencies are met."""
        for dep_id in task.dependencies:
            dep = self._tasks.get(dep_id)
            if dep and not dep.is_done:
                return False
            if dep and dep.status == TaskStatus.FAILED:
                task.status = TaskStatus.CANCELLED
                task.error = f"Dependency {dep_id} failed"
                return False
        return True
    
    async def _wait_for_dependencies(self, task: Task):
        """Wait for dependencies to complete."""
        while not self._check_dependencies(task):
            await asyncio.sleep(0.1)
            if not self._running_flag:
                return
        
        self._enqueue_task(task)
    
    async def _worker_loop(self):
        """Main worker loop."""
        while self._running_flag:
            try:
                # Get next task
                task = await self._get_next_task()
                
                if task:
                    # Run task
                    asyncio.create_task(self._run_task(task))
                
                await asyncio.sleep(0.01)  # Prevent CPU spinning
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)
    
    async def _get_next_task(self) -> Optional[Task]:
        """Get next task from queue."""
        while self._running_flag:
            with self._lock:
                if self._pending:
                    task = heapq.heappop(self._pending)
                    # Skip cancelled tasks
                    if task.status == TaskStatus.CANCELLED:
                        continue
                    return task
            
            await asyncio.sleep(0.1)
        
        return None
    
    async def _scheduler_loop(self):
        """Process scheduled tasks."""
        while self._running_flag:
            try:
                now = time.time()
                
                with self._lock:
                    while self._scheduled and self._scheduled[0].run_at <= now:
                        scheduled = heapq.heappop(self._scheduled)
                        if self._check_dependencies(scheduled.task):
                            self._enqueue_task(scheduled.task)
                        else:
                            # Reschedule
                            asyncio.create_task(
                                self._wait_for_dependencies(scheduled.task)
                            )
                
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(1)
    
    async def _run_task(self, task: Task):
        """Execute a task."""
        if task.id in self._running:
            return
        
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self._stats["running"] += 1
        
        self._running[task.id] = asyncio.current_task()
        
        try:
            # Execute with timeout
            if asyncio.iscoroutinefunction(task.func):
                result = await asyncio.wait_for(
                    task.func(*task.args, **task.kwargs),
                    timeout=task.timeout
                )
            else:
                # Run sync function in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: task.func(*task.args, **task.kwargs)
                )
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self._stats["completed"] += 1
            
            # Callbacks
            for callback in self._on_complete.get(task.name, []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(task)
                    else:
                        callback(task)
                except Exception as e:
                    logger.error(f"Complete callback error: {e}")
            
            logger.debug(f"Task completed: {task.id}")
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = f"Task timed out after {task.timeout}s"
            self._handle_retry(task)
            
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            self._handle_retry(task)
            
            # Callbacks
            for callback in self._on_failure.get(task.name, []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(task)
                    else:
                        callback(task)
                except Exception as e:
                    logger.error(f"Failure callback error: {e}")
        
        finally:
            self._running.pop(task.id, None)
            self._stats["running"] -= 1
    
    def _handle_retry(self, task: Task):
        """Handle task retry."""
        task.completed_at = time.time()
        
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            # Exponential backoff
            delay = min(2 ** task.retry_count, 60)
            task.started_at = None
            task.error = None
            
            # Reschedule
            asyncio.create_task(self._reschedule_task(task, delay))
            
            logger.info(f"Task {task.id} rescheduled, attempt {task.retry_count}")
        else:
            self._stats["failed"] += 1
            logger.error(f"Task {task.id} failed after {task.retry_count} retries: {task.error}")
    
    async def _reschedule_task(self, task: Task, delay: float):
        """Reschedule task with delay."""
        await asyncio.sleep(delay)
        if self._running_flag and task.status == TaskStatus.PENDING:
            self._enqueue_task(task)
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        if task.is_done:
            return False
        
        task.status = TaskStatus.CANCELLED
        
        # Cancel if running
        if task_id in self._running:
            self._running[task_id].cancel()
        
        return True
    
    async def get_status(self, task_id: str) -> Optional[Task]:
        """Get task status."""
        return self._tasks.get(task_id)
    
    async def get_result(self, task_id: str, timeout: float = 30) -> Any:
        """Get task result, waiting if needed."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        
        if task.is_done:
            if task.status == TaskStatus.COMPLETED:
                return task.result
            else:
                raise Exception(task.error or "Task failed")
        
        # Wait for completion
        start = time.time()
        while time.time() - start < timeout:
            if task.is_done:
                if task.status == TaskStatus.COMPLETED:
                    return task.result
                else:
                    raise Exception(task.error or "Task failed")
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Task not completed within {timeout}s")
    
    def on_complete(self, task_name: str, callback: Callable):
        """Register completion callback."""
        self._on_complete[task_name].append(callback)
    
    def on_failure(self, task_name: str, callback: Callable):
        """Register failure callback."""
        self._on_failure[task_name].append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            **self._stats,
            "pending": len(self._pending),
            "scheduled": len(self._scheduled),
            "running": len(self._running)
        }
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """List tasks."""
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]


# Global task queue instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """Get global task queue instance."""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
