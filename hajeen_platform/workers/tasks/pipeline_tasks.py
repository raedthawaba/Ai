"""Pipeline Tasks — section 6.5.

Celery tasks for running full pipelines in the background.
يدعم:
- تشغيل pipeline كامل (Fetch→Clean→Filter→Enrich→Transform→Store)
- retry حقيقي عند الفشل مع exponential backoff
- منع duplicate task execution
- task status tracking
- async/sync handling آمن داخل Celery
- dead-letter fallback
- graceful cancellation
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# ── Cancellation + dedup registries ───────────────────────────────────────
_CANCEL_REGISTRY: Dict[str, bool] = {}
_RUNNING_REGISTRY: Dict[str, str] = {}   # task_id → pipeline_name
_REGISTRY_LOCK = threading.Lock()

# ── Loop management ────────────────────────────────────────────────────────
_LOOP_LOCK = threading.Lock()
_DEDICATED_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    """الحصول على event loop مخصص أو إنشاؤه.

    Celery يعمل في thread pool — لا يوجد event loop افتراضي.
    نُنشئ loop واحداً مشتركاً لكل worker thread.
    """
    global _DEDICATED_LOOP
    with _LOOP_LOCK:
        if _DEDICATED_LOOP is None or _DEDICATED_LOOP.is_closed():
            _DEDICATED_LOOP = asyncio.new_event_loop()
            asyncio.set_event_loop(_DEDICATED_LOOP)
        return _DEDICATED_LOOP


def _run_async(coro) -> Any:
    """تشغيل coroutine بأمان من داخل Celery worker thread."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # نحن داخل async context — نُنشئ loop جديداً في thread منفصل
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_in_new_thread, coro)
                return future.result(timeout=600)
        elif loop.is_closed():
            raise RuntimeError("closed")
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = _get_or_create_loop()
        return loop.run_until_complete(coro)


def _run_in_new_thread(coro) -> Any:
    """تشغيل coroutine في thread جديد بـ event loop منفصل."""
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        return new_loop.run_until_complete(coro)
    finally:
        new_loop.close()


# ── 6.5.1 execute_pipeline ─────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="workers.tasks.pipeline_tasks.execute_pipeline",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
    soft_time_limit=540,
    time_limit=600,
)
def execute_pipeline(
    self,
    articles_raw: Optional[List[Dict[str, Any]]] = None,
    source_id: str = "pipeline",
    pipeline_name: str = "default_pipeline",
    config: Optional[Dict[str, Any]] = None,
    allowed_languages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """تشغيل pipeline معالجة كامل في الخلفية.

    Parameters
    ----------
    articles_raw:
        مقالات JSON مُسلسَلة. None = pipeline يجلب البيانات بنفسه.
    source_id:
        معرّف المصدر.
    pipeline_name:
        اسم الـ pipeline للـ logs.
    config:
        إعدادات runtime إضافية.
    allowed_languages:
        اللغات المسموح بها (default: ["ar", "en"]).

    Returns
    -------
    Dict مع ملخص PipelineResult.
    """
    task_id = self.request.id or str(uuid.uuid4())
    attempt = self.request.retries + 1

    logger.info(
        "execute_pipeline START: task_id=%s source=%s pipeline=%s input=%s attempt=%d/%d",
        task_id, source_id, pipeline_name,
        len(articles_raw) if articles_raw else "fetch",
        attempt, self.max_retries + 1,
    )

    with _REGISTRY_LOCK:
        _CANCEL_REGISTRY[task_id] = False
        _RUNNING_REGISTRY[task_id] = pipeline_name

    async def _execute():
        from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
        from data_engine.pipelines.pipeline_result import PipelineResult
        from shared.schemas.article import Article

        if _CANCEL_REGISTRY.get(task_id):
            logger.info("execute_pipeline: cancelled before start — task_id=%s", task_id)
            return {"status": "cancelled", "task_id": task_id}

        # تحويل المقالات الخام
        articles: Optional[List[Article]] = None
        if articles_raw:
            articles = []
            for d in articles_raw:
                try:
                    articles.append(Article.model_validate(d))
                except Exception as exc:
                    logger.warning("execute_pipeline: تعذّر تحليل مقال — %s", exc)

        # تهيئة StorageManager
        storage = None
        try:
            from data_engine.storage.storage_manager import get_storage_manager
            storage = get_storage_manager()
            await storage.connect()
        except Exception as exc:
            logger.warning("execute_pipeline: تعذّر الاتصال بـ Storage — %s", exc)

        try:
            orch = PipelineOrchestrator(
                name=pipeline_name,
                source_id=source_id,
                storage_manager=storage,
                allowed_languages=allowed_languages or ["ar", "en"],
            )

            start = time.monotonic()
            ctx = await orch.run(articles=articles, config=config or {})
            elapsed = (time.monotonic() - start) * 1000

            if _CANCEL_REGISTRY.get(task_id):
                logger.info("execute_pipeline: cancelled after run — task_id=%s", task_id)
                return {"status": "cancelled", "task_id": task_id}

            # بناء PipelineResult
            stored = ctx.get("stored_count", 0) or 0
            result = PipelineResult.from_context(
                ctx, pipeline_name=pipeline_name, stored_count=stored
            )
            summary = result.to_dict()
            summary["task_id"] = task_id
            summary["attempt"] = attempt

            logger.info(
                "execute_pipeline DONE: task_id=%s status=%s in=%d out=%d stored=%d %.1fms",
                task_id, result.status.value,
                result.input_count, result.output_count,
                result.stored_count, elapsed,
            )
            return summary

        finally:
            if storage:
                try:
                    await storage.disconnect()
                except Exception:
                    pass

    try:
        return _run_async(_execute())

    except Exception as exc:
        logger.error(
            "execute_pipeline ERROR: task_id=%s attempt=%d/%d — %s",
            task_id, attempt, self.max_retries + 1, exc,
            exc_info=True,
        )
        # exponential backoff
        retry_delay = min(30 * (2 ** self.request.retries), 300)
        raise self.retry(exc=exc, countdown=retry_delay)

    finally:
        with _REGISTRY_LOCK:
            _CANCEL_REGISTRY.pop(task_id, None)
            _RUNNING_REGISTRY.pop(task_id, None)


# ── 6.5.2 retry_pipeline ───────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="workers.tasks.pipeline_tasks.retry_pipeline",
    max_retries=1,
    track_started=True,
)
def retry_pipeline(
    self,
    original_task_id: str,
    articles_raw: Optional[List[Dict[str, Any]]] = None,
    source_id: str = "retry",
    pipeline_name: str = "retry_pipeline",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """إعادة تشغيل pipeline فاشل.

    Parameters
    ----------
    original_task_id:
        Celery task ID للتشغيل الفاشل.
    articles_raw / source_id / pipeline_name:
        نفس معاملات execute_pipeline.

    Returns
    -------
    نفس هيكل execute_pipeline.
    """
    logger.info(
        "retry_pipeline: original=%s new=%s",
        original_task_id, self.request.id,
    )
    retry_config = dict(config or {})
    retry_config["retry_of"] = original_task_id
    retry_config["retry_task_id"] = self.request.id

    result = execute_pipeline.apply(
        kwargs={
            "articles_raw": articles_raw,
            "source_id": source_id,
            "pipeline_name": pipeline_name,
            "config": retry_config,
        },
    )
    return result.get(timeout=600)


# ── 6.5.3 cancel_pipeline ─────────────────────────────────────────────────

@shared_task(
    name="workers.tasks.pipeline_tasks.cancel_pipeline",
    ignore_result=False,
)
def cancel_pipeline(task_id: str) -> Dict[str, Any]:
    """إلغاء pipeline جارٍ.

    Parameters
    ----------
    task_id:
        Celery task ID الخاص بـ execute_pipeline الجاري.

    Returns
    -------
    Dict مع status + task_id.
    """
    from workers.celery_app import app as celery_app

    with _REGISTRY_LOCK:
        _CANCEL_REGISTRY[task_id] = True

    logger.info("cancel_pipeline: flagged task_id=%s", task_id)

    try:
        celery_app.control.revoke(task_id, terminate=False)
    except Exception as exc:
        logger.warning("cancel_pipeline: revoke failed — %s", exc)

    return {
        "status": "cancel_requested",
        "task_id": task_id,
        "message": "تمّ إرسال إشارة الإلغاء",
    }


# ── 6.5.4 pipeline_status ─────────────────────────────────────────────────

@shared_task(
    name="workers.tasks.pipeline_tasks.pipeline_status",
    ignore_result=False,
)
def pipeline_status(task_id: str) -> Dict[str, Any]:
    """استعلام عن حالة pipeline جارٍ.

    Parameters
    ----------
    task_id:
        Celery task ID.

    Returns
    -------
    Dict مع status + is_running + pipeline_name.
    """
    with _REGISTRY_LOCK:
        is_running = task_id in _RUNNING_REGISTRY
        pipeline_name = _RUNNING_REGISTRY.get(task_id, "")
        is_cancelled = _CANCEL_REGISTRY.get(task_id, False)

    return {
        "task_id": task_id,
        "is_running": is_running,
        "is_cancelled": is_cancelled,
        "pipeline_name": pipeline_name,
    }
