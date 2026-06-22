"""Celery Configuration — يدعم وضع in-memory بدون Redis لتطوير محلي.

للتشغيل بدون Redis:
    export CELERY_USE_MEMORY=1
    celery -A workers.celery_app worker --loglevel=info

للتشغيل مع Redis:
    export REDIS_URL=redis://localhost:6379/0
    celery -A workers.celery_app worker --loglevel=info
"""
from __future__ import annotations

import os
from datetime import timedelta

# ── Broker & Backend ────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# الوضع الافتراضي: in-memory إذا لم يكن Redis متاحاً
_use_memory = os.getenv("CELERY_USE_MEMORY", "1").lower() in ("1", "true", "yes")

if _use_memory:
    # in-memory broker للتطوير المحلي بدون Redis
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
else:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# ── Serialization ───────────────────────────────────────────────────────────
TASK_SERIALIZER = "json"
RESULT_SERIALIZER = "json"
ACCEPT_CONTENT = ["json"]

# ── Timezone ─────────────────────────────────────────────────────────────────
TIMEZONE = "UTC"
ENABLE_UTC = True

# ── Task routing ─────────────────────────────────────────────────────────────
TASK_DEFAULT_QUEUE = "default"
TASK_QUEUES = {
    "default":          {"exchange": "default",          "routing_key": "default"},
    "ingestion":        {"exchange": "ingestion",        "routing_key": "ingestion"},
    "processing":       {"exchange": "processing",       "routing_key": "processing"},
    "pipeline":         {"exchange": "pipeline",         "routing_key": "pipeline"},
    "monitoring":       {"exchange": "monitoring",       "routing_key": "monitoring"},
    # Phase 8 — AI Inference Queues
    "inference":        {"exchange": "inference",        "routing_key": "inference"},
    "inference_batch":  {"exchange": "inference_batch",  "routing_key": "inference_batch"},
    "inference_heavy":  {"exchange": "inference_heavy",  "routing_key": "inference_heavy"},
}

TASK_ROUTES = {
    "workers.tasks.ingestion_tasks.*":  {"queue": "ingestion"},
    "workers.tasks.processing_tasks.*": {"queue": "processing"},
    "workers.tasks.pipeline_tasks.*":   {"queue": "pipeline"},
    # Phase 8 — AI inference routing
    "inference.async_infer":            {"queue": "inference"},
    "inference.rag_chat":               {"queue": "inference"},
    "inference.batch_infer":            {"queue": "inference_batch"},
    "inference.analyze_document":       {"queue": "inference_heavy"},
}

# ── Retry ────────────────────────────────────────────────────────────────────
TASK_MAX_RETRIES = int(os.getenv("TASK_MAX_RETRIES", "3"))
TASK_DEFAULT_RETRY_DELAY = int(os.getenv("TASK_RETRY_DELAY", "30"))
TASK_ACKS_LATE = True
TASK_REJECT_ON_WORKER_LOST = True

# ── Results ──────────────────────────────────────────────────────────────────
RESULT_EXPIRES = int(os.getenv("RESULT_EXPIRES", str(60 * 60 * 24)))
TASK_STORE_EAGER_RESULT = True

# ── Worker ────────────────────────────────────────────────────────────────────
WORKER_PREFETCH_MULTIPLIER = int(os.getenv("WORKER_PREFETCH", "4"))
WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("WORKER_MAX_TASKS", "1000"))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))

# ── Monitoring ────────────────────────────────────────────────────────────────
WORKER_SEND_TASK_EVENTS = True
TASK_SEND_SENT_EVENT = True

# ── Beat schedule ─────────────────────────────────────────────────────────────
BEAT_SCHEDULE = {
    "health-check-every-5-min": {
        "task": "workers.tasks.ingestion_tasks.health_check_task",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "monitoring"},
    },
}
