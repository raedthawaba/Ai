"""Celery Application — section 6.2.

Single Celery app instance. Imports settings from celery_config.py
and auto-discovers tasks in workers/tasks/.

يدعم:
- graceful shutdown مع حفظ الحالة
- memory broker (بدون Redis) للتطوير المحلي
- signal handlers آمنة
- lifecycle hooks شاملة
"""
from __future__ import annotations

import logging
import os
import signal
import sys

from celery import Celery
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_ready,
    worker_shutdown,
    worker_process_init,
)
from dotenv import load_dotenv

load_dotenv()

from workers import celery_config  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = Celery("hajeen_workers")
app.config_from_object(celery_config, namespace="")

# Auto-discover tasks
app.autodiscover_tasks(["workers.tasks"])

# ---------------------------------------------------------------------------
# Worker lifecycle signals
# ---------------------------------------------------------------------------

@worker_process_init.connect
def on_worker_process_init(**kwargs):  # type: ignore[no-untyped-def]
    """تهيئة worker process — إعداد logging وإعدادات عامة."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Hajeen worker process initialized — PID=%d", os.getpid())


@worker_ready.connect
def on_worker_ready(sender, **kwargs):  # type: ignore[no-untyped-def]
    queues = list(getattr(celery_config, "TASK_QUEUES", {}).keys())
    logger.info(
        "Hajeen worker ready — PID=%d queues=[%s]",
        os.getpid(),
        ", ".join(queues),
    )


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):  # type: ignore[no-untyped-def]
    """Graceful shutdown — حفظ الحالة وإغلاق الموارد."""
    logger.info("Hajeen worker shutting down gracefully — PID=%d", os.getpid())
    try:
        # إغلاق StorageManager إذا كان متصلاً
        import asyncio
        from data_engine.storage.storage_manager import get_storage_manager
        sm = get_storage_manager()
        if sm._connected:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(sm.disconnect())
            loop.close()
            logger.info("worker_shutdown: StorageManager أُغلق بأمان")
    except Exception as exc:
        logger.warning("worker_shutdown: تعذّر إغلاق StorageManager — %s", exc)

    logger.info("Hajeen worker shutdown complete ✓")


# ---------------------------------------------------------------------------
# Task lifecycle signals
# ---------------------------------------------------------------------------

@task_prerun.connect
def on_task_prerun(task_id, task, args, kwargs, **extras):  # type: ignore[no-untyped-def]
    logger.info(
        "TASK_START id=%s name=%s",
        task_id,
        task.name,
    )


@task_postrun.connect
def on_task_postrun(task_id, task, retval, state, **extras):  # type: ignore[no-untyped-def]
    logger.info(
        "TASK_DONE  id=%s name=%s state=%s",
        task_id,
        task.name,
        state,
    )


@task_retry.connect
def on_task_retry(request, reason, einfo, **extras):  # type: ignore[no-untyped-def]
    logger.warning(
        "TASK_RETRY id=%s name=%s reason=%s retries=%d",
        request.id,
        request.task,
        reason,
        request.retries,
    )


@task_failure.connect
def on_task_failure(task_id, exception, traceback, sender, **extras):  # type: ignore[no-untyped-def]
    logger.error(
        "TASK_FAIL  id=%s name=%s error=%s",
        task_id,
        sender.name,
        exception,
    )
    # Dead-letter: تسجيل المهام الفاشلة في ملف
    try:
        import json
        from pathlib import Path
        dl_path = Path("logs/dead_letter_tasks.jsonl")
        dl_path.parent.mkdir(parents=True, exist_ok=True)
        import time
        record = {
            "task_id": task_id,
            "task_name": sender.name,
            "error": str(exception),
            "timestamp": time.time(),
        }
        with open(dl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("dead_letter write error: %s", exc)


# ---------------------------------------------------------------------------
# Graceful shutdown signal handlers
# ---------------------------------------------------------------------------

def _graceful_shutdown(signum, frame):
    """إغلاق آمن عند SIGTERM / SIGINT."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info("Hajeen Celery: received %s — initiating graceful shutdown", sig_name)
    app.control.broadcast("shutdown", destination=None)
    sys.exit(0)


# تسجيل handlers للإشارات
try:
    signal.signal(signal.SIGTERM, _graceful_shutdown)
except OSError:
    pass  # لا يمكن تسجيل SIGTERM في بعض البيئات

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.start()
