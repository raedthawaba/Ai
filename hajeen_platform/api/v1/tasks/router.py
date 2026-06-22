"""Task & Job API Endpoints — section 6.12.

Endpoints:
  POST /channels/{channel_id}/trigger   — trigger channel ingestion
  GET  /tasks/{task_id}                 — get task status
  GET  /jobs                            — list scheduled jobs
  POST /jobs/{job_id}/pause             — pause a job
  POST /jobs/{job_id}/resume            — resume a job
  POST /pipelines/execute               — execute a pipeline
  POST /pipelines/{task_id}/cancel      — cancel a pipeline
  GET  /monitor/summary                 — monitoring summary
  GET  /monitor/running                 — running tasks
  GET  /monitor/failed                  — failed tasks
  GET  /workers/status                  — worker queue status
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks & Scheduling"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TriggerChannelResponse(BaseModel):
    task_id: str
    channel_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    traceback: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    name: str
    next_run: Optional[str]
    paused: bool
    trigger: str


class PipelineExecuteRequest(BaseModel):
    source_id: str = "api"
    pipeline_name: str = "api_pipeline"
    articles: Optional[List[Dict[str, Any]]] = None
    allowed_languages: List[str] = ["ar", "en"]
    config: Dict[str, Any] = {}


class PipelineExecuteResponse(BaseModel):
    task_id: str
    status: str
    message: str


class ScheduleChannelRequest(BaseModel):
    cron_expression: str = "0 */6 * * *"
    enabled: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_celery_app():
    from workers.celery_app import app
    return app


def _get_scheduler():
    from data_engine.ingestion.schedulers.cron_scheduler import get_scheduler
    return get_scheduler()


def _get_monitor():
    from monitoring.task_monitor import TaskMonitor
    return TaskMonitor()


def _get_job_store():
    from data_engine.storage.metadata_store.job_store import JobStore
    return JobStore()


# ---------------------------------------------------------------------------
# Channel triggers
# ---------------------------------------------------------------------------

@router.post(
    "/channels/{channel_id}/trigger",
    response_model=TriggerChannelResponse,
    summary="Trigger channel ingestion",
)
async def trigger_channel(
    channel_id: str = Path(..., description="Channel ID to trigger"),
) -> TriggerChannelResponse:
    """Dispatch a background ingestion task for the given channel."""
    from workers.tasks.ingestion_tasks import run_channel_ingestion
    from data_engine.channels.registry import ChannelRegistry

    channel = ChannelRegistry.get(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id!r}")

    try:
        async_result = run_channel_ingestion.delay(channel_id)
        logger.info("trigger_channel: dispatched task_id=%s for channel=%s", async_result.id, channel_id)
        return TriggerChannelResponse(
            task_id=async_result.id,
            channel_id=channel_id,
            status="queued",
            message=f"Ingestion task queued for channel '{channel.config.name}'",
        )
    except Exception as exc:
        logger.error("trigger_channel error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/channels/{channel_id}/schedule",
    summary="Schedule periodic channel ingestion",
)
async def schedule_channel(
    channel_id: str = Path(..., description="Channel ID"),
    request: ScheduleChannelRequest = Body(...),
) -> Dict[str, Any]:
    """Schedule recurring channel ingestion using a cron expression."""
    from data_engine.channels.registry import ChannelRegistry
    from data_engine.storage.metadata_store.job_store import JobStore, ScheduledJob

    channel = ChannelRegistry.get(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id!r}")

    try:
        scheduler = _get_scheduler()
        job_id = scheduler.schedule_channel(channel_id, request.cron_expression)

        store = _get_job_store()
        job_def = ScheduledJob(
            job_id=job_id,
            name=f"Channel: {channel.config.name}",
            channel_id=channel_id,
            trigger_type="cron",
            trigger_value=request.cron_expression,
            enabled=request.enabled,
        )
        store.save_job(job_def)

        return {
            "job_id": job_id,
            "channel_id": channel_id,
            "cron_expression": request.cron_expression,
            "status": "scheduled",
            "message": f"Channel '{channel.config.name}' scheduled",
        }
    except Exception as exc:
        logger.error("schedule_channel error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Task status
# ---------------------------------------------------------------------------

@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get task status",
)
async def get_task_status(
    task_id: str = Path(..., description="Celery task ID"),
) -> TaskStatusResponse:
    """Return the status and result of a Celery task."""
    celery_app = _get_celery_app()
    try:
        result = celery_app.AsyncResult(task_id)
        status = result.status.lower()

        response = TaskStatusResponse(task_id=task_id, status=status)

        if result.ready():
            if result.successful():
                response.result = result.result if isinstance(result.result, dict) else {"value": str(result.result)}
            elif result.failed():
                response.error = str(result.result)
                response.traceback = result.traceback

        # Augment with monitor data
        try:
            monitor = _get_monitor()
            record = monitor.get_task(task_id)
            if record:
                response.status = record.get("status", status)
        except Exception:
            pass

        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

@router.post(
    "/pipelines/execute",
    response_model=PipelineExecuteResponse,
    summary="Execute a pipeline",
)
async def execute_pipeline_endpoint(
    request: PipelineExecuteRequest = Body(...),
) -> PipelineExecuteResponse:
    """Submit a pipeline execution task to the background queue."""
    from workers.tasks.pipeline_tasks import execute_pipeline

    try:
        result = execute_pipeline.delay(
            articles_raw=request.articles,
            source_id=request.source_id,
            pipeline_name=request.pipeline_name,
            config=request.config,
            allowed_languages=request.allowed_languages,
        )
        return PipelineExecuteResponse(
            task_id=result.id,
            status="queued",
            message=f"Pipeline '{request.pipeline_name}' submitted",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/pipelines/{task_id}/cancel",
    summary="Cancel a running pipeline",
)
async def cancel_pipeline_endpoint(
    task_id: str = Path(..., description="Task ID to cancel"),
) -> Dict[str, Any]:
    """Signal a running pipeline to stop."""
    from workers.tasks.pipeline_tasks import cancel_pipeline

    try:
        cancel_pipeline.delay(task_id)
        return {"task_id": task_id, "status": "cancel_requested"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

@router.get(
    "/jobs",
    response_model=List[JobResponse],
    summary="List scheduled jobs",
)
async def list_jobs() -> List[JobResponse]:
    """Return all scheduled jobs from the scheduler."""
    try:
        scheduler = _get_scheduler()
        jobs = scheduler.list_jobs()
        return [
            JobResponse(
                id=j["id"],
                name=j["name"],
                next_run=j.get("next_run"),
                paused=j.get("paused", False),
                trigger=j.get("trigger", ""),
            )
            for j in jobs
        ]
    except Exception as exc:
        logger.warning("list_jobs: scheduler unavailable — %s", exc)
        # Fall back to DB
        try:
            store = _get_job_store()
            db_jobs = store.list_jobs()
            return [
                JobResponse(
                    id=j.job_id, name=j.name, next_run=None,
                    paused=not j.enabled, trigger=j.trigger_value,
                )
                for j in db_jobs
            ]
        except Exception:
            return []


@router.post(
    "/jobs/{job_id}/pause",
    summary="Pause a scheduled job",
)
async def pause_job(
    job_id: str = Path(..., description="Job ID"),
) -> Dict[str, Any]:
    """Pause a scheduled job."""
    try:
        scheduler = _get_scheduler()
        paused = scheduler.pause_job(job_id)
        if not paused:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
        store = _get_job_store()
        store.update_job_status(job_id, enabled=False)
        return {"job_id": job_id, "status": "paused"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/jobs/{job_id}/resume",
    summary="Resume a paused job",
)
async def resume_job(
    job_id: str = Path(..., description="Job ID"),
) -> Dict[str, Any]:
    """Resume a paused scheduled job."""
    try:
        scheduler = _get_scheduler()
        resumed = scheduler.resume_job(job_id)
        if not resumed:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
        store = _get_job_store()
        store.update_job_status(job_id, enabled=True)
        return {"job_id": job_id, "status": "resumed"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

@router.get(
    "/monitor/summary",
    summary="Task monitoring summary",
)
async def monitoring_summary() -> Dict[str, Any]:
    """Return a dashboard summary of all task executions."""
    try:
        monitor = _get_monitor()
        return monitor.summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/monitor/running",
    summary="Running tasks",
)
async def running_tasks() -> List[Dict[str, Any]]:
    """Return currently running tasks."""
    try:
        monitor = _get_monitor()
        return monitor.running_tasks()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/monitor/failed",
    summary="Failed tasks",
)
async def failed_tasks(
    limit: int = Query(50, ge=1, le=500, description="Max records"),
) -> List[Dict[str, Any]]:
    """Return recently failed tasks."""
    try:
        monitor = _get_monitor()
        return monitor.failed_tasks(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Worker status
# ---------------------------------------------------------------------------

@router.get(
    "/workers/status",
    summary="Worker queue status",
)
async def worker_status() -> Dict[str, Any]:
    """Return Celery worker queue status."""
    celery_app = _get_celery_app()
    try:
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        stats = inspect.stats() or {}
        return {
            "workers": list(stats.keys()),
            "active_tasks": sum(len(v) for v in active.values()),
            "reserved_tasks": sum(len(v) for v in reserved.values()),
            "worker_details": {
                name: {
                    "active": len(active.get(name, [])),
                    "reserved": len(reserved.get(name, [])),
                }
                for name in stats
            },
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}
