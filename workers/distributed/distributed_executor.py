"""
Distributed Executor — high-level interface for submitting tasks to the
distributed worker fleet with automatic routing, monitoring, and result collection.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from workers.distributed.queue_router import QueueRouter, TaskPriority

logger = logging.getLogger(__name__)


class DistributedExecutor:
    """Submit tasks to the distributed fleet and collect results."""

    def __init__(
        self,
        celery_app: Any,
        queue_router: QueueRouter,
    ) -> None:
        self.celery = celery_app
        self.router = queue_router

    def submit(
        self,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        priority: Optional[TaskPriority] = None,
        task_id: Optional[str] = None,
        countdown: int = 0,
    ) -> str:
        args = args or []
        kwargs = kwargs or {}
        task_id = task_id or str(uuid.uuid4())

        route = self.router.route_task(task_name, args, kwargs, priority)

        result = self.celery.send_task(
            task_name,
            args=args,
            kwargs=kwargs,
            task_id=task_id,
            queue=route.queue.value,
            priority=route.priority.value,
            routing_key=route.routing_key,
            soft_time_limit=route.timeout,
            time_limit=route.timeout + 60,
            countdown=countdown,
            retries=0,
        )

        logger.info(
            "Task submitted: id=%s name=%s queue=%s priority=%s",
            task_id, task_name, route.queue.value, route.priority.name,
        )
        return task_id

    def submit_batch(
        self,
        tasks: List[Dict[str, Any]],
        priority: Optional[TaskPriority] = None,
    ) -> List[str]:
        task_ids: List[str] = []
        for task in tasks:
            task_id = self.submit(
                task_name=task["name"],
                args=task.get("args", []),
                kwargs=task.get("kwargs", {}),
                priority=priority or task.get("priority"),
                task_id=task.get("id"),
            )
            task_ids.append(task_id)
        return task_ids

    def get_result(
        self,
        task_id: str,
        timeout: int = 60,
        propagate: bool = True,
    ) -> Any:
        result = self.celery.AsyncResult(task_id)
        return result.get(timeout=timeout, propagate=propagate)

    def get_status(self, task_id: str) -> Dict[str, Any]:
        result = self.celery.AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
        }

    def revoke(self, task_id: str, terminate: bool = False) -> None:
        self.celery.control.revoke(task_id, terminate=terminate)
        logger.info("Revoked task %s (terminate=%s)", task_id, terminate)
