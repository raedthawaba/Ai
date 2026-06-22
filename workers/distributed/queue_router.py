"""
Distributed Queue Router — routes tasks to appropriate queues based on
task type, priority, resource requirements, and current system state.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import redis
from celery import Celery

logger = logging.getLogger(__name__)


class TaskPriority(int, Enum):
    CRITICAL = 10
    HIGH = 7
    NORMAL = 5
    LOW = 3
    BACKGROUND = 1


class QueueType(str, Enum):
    GPU = "gpu"
    CPU = "cpu"
    TRAINING = "training"
    INFERENCE = "inference"
    DATA = "data"
    DEFAULT = "default"
    DEAD_LETTER = "dead_letter"


@dataclass
class TaskRoute:
    queue: QueueType
    priority: TaskPriority
    routing_key: str
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 3600
    max_retries: int = 3


TASK_ROUTING_TABLE: Dict[str, TaskRoute] = {
    "inference.*": TaskRoute(
        queue=QueueType.GPU,
        priority=TaskPriority.HIGH,
        routing_key="gpu.inference",
        timeout=300,
        max_retries=2,
    ),
    "training.*": TaskRoute(
        queue=QueueType.TRAINING,
        priority=TaskPriority.NORMAL,
        routing_key="gpu.training",
        timeout=86400,
        max_retries=1,
    ),
    "embedding.*": TaskRoute(
        queue=QueueType.GPU,
        priority=TaskPriority.NORMAL,
        routing_key="gpu.embedding",
        timeout=600,
        max_retries=3,
    ),
    "data.*": TaskRoute(
        queue=QueueType.DATA,
        priority=TaskPriority.LOW,
        routing_key="cpu.data",
        timeout=7200,
        max_retries=3,
    ),
    "default.*": TaskRoute(
        queue=QueueType.DEFAULT,
        priority=TaskPriority.NORMAL,
        routing_key="cpu.default",
        timeout=3600,
        max_retries=3,
    ),
}


class QueueRouter:
    """Routes tasks to appropriate queues based on type and load."""

    def __init__(self, redis_client: redis.Redis, celery_app: Celery) -> None:
        self.redis = redis_client
        self.celery = celery_app
        self._load_cache: Dict[str, float] = {}

    def route_task(
        self,
        task_name: str,
        task_args: List[Any],
        task_kwargs: Dict[str, Any],
        priority: Optional[TaskPriority] = None,
    ) -> TaskRoute:
        route = self._match_route(task_name)
        if priority is not None:
            route.priority = priority

        # Adjust route based on current queue load
        if route.queue == QueueType.GPU:
            gpu_load = self._get_queue_load(QueueType.GPU)
            if gpu_load > 0.85:
                logger.warning(
                    "GPU queue overloaded (%.0f%%), routing to CPU fallback",
                    gpu_load * 100,
                )
                if not self._requires_gpu(task_name):
                    route.queue = QueueType.CPU

        return route

    def _match_route(self, task_name: str) -> TaskRoute:
        for pattern, route in TASK_ROUTING_TABLE.items():
            prefix = pattern.replace(".*", "")
            if task_name.startswith(prefix):
                return TaskRoute(
                    queue=route.queue,
                    priority=route.priority,
                    routing_key=route.routing_key,
                    timeout=route.timeout,
                    max_retries=route.max_retries,
                )
        return TASK_ROUTING_TABLE["default.*"]

    def _get_queue_load(self, queue: QueueType) -> float:
        cache_key = f"queue_load:{queue.value}"
        cached = self.redis.get(cache_key)
        if cached:
            return float(cached)

        try:
            inspect = self.celery.control.inspect()
            active = inspect.active() or {}
            scheduled = inspect.scheduled() or {}

            active_count = sum(
                len(tasks) for tasks in active.values()
                if tasks
            )
            scheduled_count = sum(
                len(tasks) for tasks in scheduled.values()
                if tasks
            )

            total = active_count + scheduled_count
            max_capacity = 100
            load = min(total / max_capacity, 1.0)

            self.redis.setex(cache_key, 10, str(load))
            return load
        except Exception:
            return 0.5

    def _requires_gpu(self, task_name: str) -> bool:
        gpu_tasks = {"inference", "training", "embedding", "generation"}
        return any(gpu_task in task_name for gpu_task in gpu_tasks)

    def get_queue_depths(self) -> Dict[str, int]:
        depths: Dict[str, int] = {}
        for queue_type in QueueType:
            if queue_type == QueueType.DEAD_LETTER:
                continue
            key = f"celery:{queue_type.value}"
            depth = self.redis.llen(key)
            depths[queue_type.value] = int(depth)
        return depths

    def rebalance_queues(self) -> Dict[str, Any]:
        depths = self.get_queue_depths()
        overloaded = {q: d for q, d in depths.items() if d > 100}
        actions: List[str] = []

        for queue, depth in overloaded.items():
            logger.info("Queue %s overloaded: %d tasks", queue, depth)
            actions.append(f"Scaled workers for {queue} queue (depth={depth})")

        return {"depths": depths, "overloaded": overloaded, "actions": actions}

    def send_to_dead_letter(
        self,
        task_id: str,
        task_name: str,
        error: str,
        original_kwargs: Dict[str, Any],
    ) -> None:
        payload = {
            "task_id": task_id,
            "task_name": task_name,
            "error": error,
            "original_kwargs": original_kwargs,
        }
        self.redis.lpush("dead_letter_queue", str(payload))
        logger.error("Task %s sent to dead letter queue: %s", task_id, error)
