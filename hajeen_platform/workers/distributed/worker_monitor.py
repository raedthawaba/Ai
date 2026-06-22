"""
Worker Monitor — tracks worker health, resource utilization, task throughput,
and triggers auto-scaling decisions.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


@dataclass
class WorkerStats:
    worker_id: str
    hostname: str
    status: str
    active_tasks: int
    processed_tasks: int
    failed_tasks: int
    cpu_percent: float
    memory_mb: float
    uptime_seconds: float
    last_heartbeat: float


class WorkerMonitor:
    """Monitors the health and performance of all workers."""

    HEARTBEAT_TIMEOUT = 60.0
    STATS_KEY_PREFIX = "worker:stats:"
    HEARTBEAT_KEY_PREFIX = "worker:heartbeat:"

    def __init__(self, redis_client: redis.Redis, celery_app: Any) -> None:
        self.redis = redis_client
        self.celery = celery_app

    def get_all_worker_stats(self) -> List[WorkerStats]:
        try:
            inspect = self.celery.control.inspect(timeout=5)
            active = inspect.active() or {}
            stats = inspect.stats() or {}
            registered = inspect.registered() or {}

            workers: List[WorkerStats] = []
            for worker_name in set(list(active.keys()) + list(stats.keys())):
                worker_stats = stats.get(worker_name, {})
                active_tasks = active.get(worker_name, [])

                hb_key = f"{self.HEARTBEAT_KEY_PREFIX}{worker_name}"
                heartbeat = self.redis.get(hb_key)
                last_hb = float(heartbeat) if heartbeat else 0.0

                total = worker_stats.get("total", {})
                processed = sum(total.values()) if total else 0

                rusage = worker_stats.get("rusage", {})
                cpu = rusage.get("utime", 0.0) + rusage.get("stime", 0.0)

                workers.append(
                    WorkerStats(
                        worker_id=worker_name,
                        hostname=worker_stats.get("hostname", worker_name),
                        status="online" if last_hb > time.time() - self.HEARTBEAT_TIMEOUT else "offline",
                        active_tasks=len(active_tasks),
                        processed_tasks=processed,
                        failed_tasks=0,
                        cpu_percent=cpu,
                        memory_mb=rusage.get("maxrss", 0) / 1024,
                        uptime_seconds=worker_stats.get("uptime", 0),
                        last_heartbeat=last_hb,
                    )
                )
            return workers
        except Exception as exc:
            logger.warning("Failed to collect worker stats: %s", exc)
            return []

    def record_heartbeat(self, worker_id: str) -> None:
        key = f"{self.HEARTBEAT_KEY_PREFIX}{worker_id}"
        self.redis.setex(key, int(self.HEARTBEAT_TIMEOUT * 2), str(time.time()))

    def detect_stale_workers(self) -> List[str]:
        stale: List[str] = []
        keys = self.redis.keys(f"{self.HEARTBEAT_KEY_PREFIX}*")
        for key in keys:
            raw = self.redis.get(key)
            if raw and float(raw) < time.time() - self.HEARTBEAT_TIMEOUT:
                worker_id = key.decode().replace(self.HEARTBEAT_KEY_PREFIX, "")
                stale.append(worker_id)
                logger.warning("Stale worker detected: %s", worker_id)
        return stale

    def get_queue_metrics(self) -> Dict[str, Any]:
        queue_names = ["default", "gpu", "training", "inference", "data", "dead_letter"]
        metrics: Dict[str, Any] = {}
        for queue in queue_names:
            length = self.redis.llen(f"celery:{queue}")
            metrics[queue] = {"depth": int(length)}
        return metrics

    def get_system_health(self) -> Dict[str, Any]:
        workers = self.get_all_worker_stats()
        online = [w for w in workers if w.status == "online"]
        stale = self.detect_stale_workers()
        queue_metrics = self.get_queue_metrics()
        total_active = sum(w.active_tasks for w in online)
        total_processed = sum(w.processed_tasks for w in online)

        return {
            "timestamp": time.time(),
            "workers": {
                "total": len(workers),
                "online": len(online),
                "stale": len(stale),
                "stale_ids": stale,
            },
            "tasks": {
                "active": total_active,
                "processed_total": total_processed,
            },
            "queues": queue_metrics,
            "healthy": len(online) > 0 and len(stale) == 0,
        }
