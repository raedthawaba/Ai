"""
Scheduler Manager — manages periodic tasks, cron jobs, and event-driven
task scheduling across the distributed worker fleet.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import redis
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    name: str
    task_path: str
    schedule: Any
    args: List[Any] = None
    kwargs: Dict[str, Any] = None
    enabled: bool = True
    description: str = ""

    def __post_init__(self):
        if self.args is None:
            self.args = []
        if self.kwargs is None:
            self.kwargs = {}


PRODUCTION_SCHEDULE: List[ScheduledTask] = [
    ScheduledTask(
        name="cleanup-expired-sessions",
        task_path="workers.tasks.maintenance.cleanup_expired_sessions",
        schedule=crontab(minute="*/30"),
        description="Remove expired user sessions",
    ),
    ScheduledTask(
        name="update-model-cache",
        task_path="workers.tasks.models.refresh_model_metadata",
        schedule=crontab(hour="*/6", minute="0"),
        description="Refresh model registry metadata",
    ),
    ScheduledTask(
        name="backup-vector-db",
        task_path="workers.tasks.storage.backup_vector_database",
        schedule=crontab(hour="2", minute="0"),
        description="Nightly vector database backup",
    ),
    ScheduledTask(
        name="aggregate-usage-metrics",
        task_path="workers.tasks.analytics.aggregate_usage",
        schedule=crontab(minute="0"),
        description="Hourly usage metric aggregation",
    ),
    ScheduledTask(
        name="health-check-external",
        task_path="workers.tasks.monitoring.check_external_services",
        schedule=crontab(minute="*/5"),
        description="Check external service availability",
    ),
    ScheduledTask(
        name="prune-dead-letter-queue",
        task_path="workers.tasks.maintenance.prune_dead_letter",
        schedule=crontab(hour="*/4", minute="30"),
        description="Process and archive dead-letter queue items",
    ),
    ScheduledTask(
        name="tenant-quota-reset",
        task_path="workers.tasks.tenants.reset_daily_quotas",
        schedule=crontab(hour="0", minute="0"),
        description="Reset daily tenant quotas at midnight UTC",
    ),
    ScheduledTask(
        name="reindex-stale-documents",
        task_path="workers.tasks.rag.reindex_stale_documents",
        schedule=crontab(hour="3", minute="0"),
        description="Reindex documents with stale embeddings",
    ),
]


class SchedulerManager:
    """Manages task scheduling with dynamic registration and monitoring."""

    def __init__(self, celery_app: Celery, redis_client: redis.Redis) -> None:
        self.celery = celery_app
        self.redis = redis_client
        self._tasks: Dict[str, ScheduledTask] = {
            t.name: t for t in PRODUCTION_SCHEDULE
        }

    def configure_beat_schedule(self) -> Dict[str, Any]:
        beat_schedule: Dict[str, Any] = {}

        for task in self._tasks.values():
            if not task.enabled:
                continue

            beat_schedule[task.name] = {
                "task": task.task_path,
                "schedule": task.schedule,
                "args": task.args,
                "kwargs": task.kwargs,
            }

        self.celery.conf.beat_schedule = beat_schedule
        logger.info("Configured %d scheduled tasks", len(beat_schedule))
        return beat_schedule

    def register_task(self, task: ScheduledTask) -> None:
        self._tasks[task.name] = task
        self.configure_beat_schedule()
        logger.info("Registered scheduled task: %s", task.name)

    def disable_task(self, task_name: str) -> bool:
        if task_name not in self._tasks:
            return False
        self._tasks[task_name].enabled = False
        self.configure_beat_schedule()
        key = f"scheduler:disabled:{task_name}"
        self.redis.set(key, "1")
        logger.info("Disabled scheduled task: %s", task_name)
        return True

    def enable_task(self, task_name: str) -> bool:
        if task_name not in self._tasks:
            return False
        self._tasks[task_name].enabled = True
        self.redis.delete(f"scheduler:disabled:{task_name}")
        self.configure_beat_schedule()
        logger.info("Enabled scheduled task: %s", task_name)
        return True

    def get_task_status(self) -> List[Dict[str, Any]]:
        status = []
        for task in self._tasks.values():
            last_run_key = f"scheduler:last_run:{task.name}"
            last_run = self.redis.get(last_run_key)
            status.append({
                "name": task.name,
                "description": task.description,
                "enabled": task.enabled,
                "last_run": float(last_run) if last_run else None,
            })
        return status


def health_check() -> None:
    """Simple health check for scheduler container."""
    import sys
    import os
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url, socket_connect_timeout=2)
    r.ping()
    print("Scheduler healthy")
    sys.exit(0)
