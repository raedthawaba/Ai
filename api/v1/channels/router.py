"""Channels Router — endpoints حقيقية لإدارة القنوات.

POST   /channels                     — إنشاء قناة
GET    /channels                     — استرجاع جميع القنوات
GET    /channels/{id}                — استرجاع قناة بالمعرّف
PUT    /channels/{id}                — تحديث قناة (body)
DELETE /channels/{id}                — حذف قناة
POST   /channels/{id}/trigger        — تشغيل pipeline القناة
GET    /channels/{id}/status         — حالة القناة
GET    /channels/{id}/audit          — سجل audit للقناة
PATCH  /channels/{id}/pause          — إيقاف مؤقت للقناة
PATCH  /channels/{id}/resume         — استئناف القناة
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from data_engine.channels.builder import ChannelBuilder
from data_engine.channels.registry import ChannelRegistry
from shared.schemas.channel import ChannelConfig, ChannelStatus, SourceConfig, ScheduleConfig
from shared.utils.id_generator import generate_channel_id
from shared.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────

class SourceConfigIn(BaseModel):
    url: str = Field(..., description="URL المصدر")
    type: str = Field(..., description="نوع المصدر: rss, api, demo, placeholder")
    params: Dict[str, Any] = Field(default_factory=dict)


class ScheduleConfigIn(BaseModel):
    cron: str = Field(default="0 * * * *", description="تعبير cron")
    enabled: bool = True
    timezone: str = "UTC"


class CreateChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, description="اسم القناة")
    description: str = Field(default="", description="وصف القناة")
    source: SourceConfigIn
    schedule: Optional[ScheduleConfigIn] = None


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    status: Optional[str] = None
    schedule: Optional[ScheduleConfigIn] = None


class ChannelResponse(BaseModel):
    id: str
    name: str
    description: str
    source_type: str
    source_url: str
    status: str
    total_runs: int = 0
    total_fetched: int = 0
    last_run: Optional[str] = None
    created_at: str
    updated_at: str


class TriggerResponse(BaseModel):
    channel_id: str
    run_id: str
    status: str
    message: str
    fetched: int = 0
    processed: int = 0
    stored: int = 0
    duration_ms: float = 0.0
    errors: List[str] = Field(default_factory=list)


class StatusResponse(BaseModel):
    channel_id: str
    name: str
    status: str
    last_run: Optional[str] = None
    total_runs: int = 0
    total_fetched: int = 0
    total_processed: int = 0
    total_stored: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    last_error: Optional[str] = None


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _channel_to_response(channel) -> ChannelResponse:
    cfg = channel.config
    stats = cfg.stats
    return ChannelResponse(
        id=cfg.id,
        name=cfg.name,
        description=cfg.description or "",
        source_type=cfg.source.type,
        source_url=str(cfg.source.url),
        status=cfg.status.value,
        total_runs=stats.total_runs,
        total_fetched=stats.total_fetched,
        last_run=stats.last_run_at.isoformat() if stats.last_run_at else (
            channel.last_run.isoformat() if channel.last_run else None
        ),
        created_at=cfg.created_at.isoformat(),
        updated_at=cfg.updated_at.isoformat(),
    )


def _config_to_response(cfg: ChannelConfig) -> ChannelResponse:
    stats = cfg.stats
    return ChannelResponse(
        id=cfg.id,
        name=cfg.name,
        description=cfg.description or "",
        source_type=cfg.source.type,
        source_url=str(cfg.source.url),
        status=cfg.status.value,
        total_runs=stats.total_runs,
        total_fetched=stats.total_fetched,
        last_run=stats.last_run_at.isoformat() if stats.last_run_at else None,
        created_at=cfg.created_at.isoformat(),
        updated_at=cfg.updated_at.isoformat(),
    )


def _resolve_status(status_str: str) -> ChannelStatus:
    """تحويل نص الحالة إلى ChannelStatus مع رسالة خطأ واضحة."""
    try:
        return ChannelStatus(status_str.lower())
    except ValueError:
        valid = [s.value for s in ChannelStatus]
        raise HTTPException(
            status_code=422,
            detail=f"حالة غير صالحة: '{status_str}'. القيم المتاحة: {valid}",
        )


# ─────────────────────────────────────────────
# POST /channels — إنشاء قناة
# ─────────────────────────────────────────────

@router.post("", response_model=ChannelResponse, status_code=201)
async def create_channel(body: CreateChannelRequest):
    """إنشاء قناة جديدة وتسجيلها مع الحفظ في SQLite."""
    channel_id = generate_channel_id()

    schedule_cfg = None
    if body.schedule:
        try:
            schedule_cfg = ScheduleConfig(
                cron=body.schedule.cron,
                enabled=body.schedule.enabled,
                timezone=body.schedule.timezone,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"تكوين الجدولة غير صالح: {exc}")

    try:
        source_cfg = SourceConfig(
            url=body.source.url,  # type: ignore[arg-type]
            type=body.source.type,
            params=body.source.params,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"تكوين المصدر غير صالح: {exc}")

    now = utc_now()
    config = ChannelConfig(
        id=channel_id,
        name=body.name,
        description=body.description,
        source=source_cfg,
        schedule=schedule_cfg,
        status=ChannelStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    try:
        channel = await ChannelBuilder.create_from_config(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"خطأ في إنشاء القناة: {exc}")

    try:
        ChannelRegistry.register(channel, actor="api")
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    logger.info("create_channel: أُنشئت القناة %s (%s)", channel_id, body.name)
    return _channel_to_response(channel)


# ─────────────────────────────────────────────
# GET /channels
# ─────────────────────────────────────────────

@router.get("", response_model=List[ChannelResponse])
async def list_channels(
    status: Optional[str] = Query(default=None, description="فلترة حسب الحالة"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """استرجاع جميع القنوات المسجّلة مع دعم الفلترة."""
    channels = ChannelRegistry.list_all()
    responses: List[ChannelResponse] = []

    if channels:
        for ch in channels:
            if status and ch.config.status.value != status.lower():
                continue
            responses.append(_channel_to_response(ch))
    else:
        db_configs = ChannelRegistry.list_from_db()
        for cfg in db_configs:
            if status and cfg.status.value != status.lower():
                continue
            responses.append(_config_to_response(cfg))

    return responses[:limit]


# ─────────────────────────────────────────────
# GET /channels/{channel_id}
# ─────────────────────────────────────────────

@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str):
    """استرجاع قناة بمعرّفها."""
    channel = ChannelRegistry.get(channel_id)
    if channel:
        return _channel_to_response(channel)

    for cfg in ChannelRegistry.list_from_db():
        if cfg.id == channel_id:
            return _config_to_response(cfg)

    raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")


# ─────────────────────────────────────────────
# PUT /channels/{channel_id} — تحديث القناة
# ─────────────────────────────────────────────

@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(channel_id: str, body: UpdateChannelRequest):
    """تحديث بيانات أو حالة قناة عبر request body."""
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")

    # تحديث الاسم
    if body.name is not None:
        channel.config.name = body.name.strip()

    # تحديث الوصف
    if body.description is not None:
        channel.config.description = body.description

    # تحديث الجدولة
    if body.schedule is not None:
        try:
            channel.config.schedule = ScheduleConfig(
                cron=body.schedule.cron,
                enabled=body.schedule.enabled,
                timezone=body.schedule.timezone,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"تكوين الجدولة غير صالح: {exc}")

    # تحديث الحالة
    if body.status is not None:
        new_status = _resolve_status(body.status)
        try:
            ChannelRegistry.update_status(channel_id, new_status, actor="api")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    channel.config.updated_at = utc_now()

    # حفظ التحديثات في SQLite
    from data_engine.channels.registry import _save_channel_to_db
    _save_channel_to_db(channel.config)

    logger.info("update_channel: تمّ تحديث القناة %s", channel_id)
    return _channel_to_response(channel)


# ─────────────────────────────────────────────
# DELETE /channels/{channel_id}
# ─────────────────────────────────────────────

@router.delete("/{channel_id}", status_code=204)
async def delete_channel(channel_id: str):
    """حذف قناة بمعرّفها."""
    try:
        ChannelRegistry.unregister(channel_id, actor="api")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ─────────────────────────────────────────────
# PATCH /channels/{channel_id}/pause
# ─────────────────────────────────────────────

@router.patch("/{channel_id}/pause", response_model=ChannelResponse)
async def pause_channel(channel_id: str):
    """إيقاف مؤقت للقناة (PAUSED)."""
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")

    if channel.config.status == ChannelStatus.PAUSED:
        raise HTTPException(status_code=400, detail="القناة متوقفة مؤقتاً بالفعل")

    ChannelRegistry.update_status(channel_id, ChannelStatus.PAUSED, actor="api")
    logger.info("pause_channel: القناة %s → PAUSED", channel_id)
    return _channel_to_response(channel)


# ─────────────────────────────────────────────
# PATCH /channels/{channel_id}/resume
# ─────────────────────────────────────────────

@router.patch("/{channel_id}/resume", response_model=ChannelResponse)
async def resume_channel(channel_id: str):
    """استئناف قناة متوقفة مؤقتاً."""
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")

    if channel.config.status != ChannelStatus.PAUSED:
        raise HTTPException(status_code=400, detail="القناة ليست في حالة PAUSED")

    ChannelRegistry.update_status(channel_id, ChannelStatus.ACTIVE, actor="api")
    logger.info("resume_channel: القناة %s → ACTIVE", channel_id)
    return _channel_to_response(channel)


# ─────────────────────────────────────────────
# POST /channels/{channel_id}/trigger
# ─────────────────────────────────────────────

@router.post("/{channel_id}/trigger", response_model=TriggerResponse)
async def trigger_channel(channel_id: str):
    """تشغيل pipeline القناة ومعالجة البيانات end-to-end."""
    # استعادة القناة من الذاكرة أو SQLite
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        await ChannelRegistry.restore_from_db()
        channel = ChannelRegistry.get(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")

    if channel.config.status == ChannelStatus.INACTIVE:
        raise HTTPException(status_code=400, detail="القناة غير نشطة — غيّر الحالة إلى active أولاً")

    if channel.config.status == ChannelStatus.PAUSED:
        raise HTTPException(status_code=400, detail="القناة متوقفة مؤقتاً — استخدم /resume أولاً")

    run_id = str(uuid.uuid4())[:8]
    start = time.monotonic()
    errors_list: List[str] = []

    ChannelRegistry.update_status(channel_id, ChannelStatus.ACTIVE, actor="trigger")

    try:
        from data_engine.storage.storage_manager import get_storage_manager

        storage = get_storage_manager()
        try:
            await storage.connect()
        except Exception as exc:
            logger.warning("trigger: تعذّر الاتصال بـ StorageManager — %s", exc)
            storage = None

        from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(
            name=f"api_trigger:{channel.config.name}",
            source_id=channel.config.id,
            storage_manager=storage,
            allowed_languages=["ar", "en"],
        )

        # جلب البيانات
        try:
            fetch_result = await channel.fetch()
            articles = fetch_result.articles
        except Exception as exc:
            logger.error("trigger: فشل fetch للقناة %s — %s", channel_id, exc)
            errors_list.append(f"fetch: {exc}")
            articles = []

        # تشغيل الـ pipeline
        processed = 0
        stored = 0

        if articles:
            context = await orchestrator.run(articles=articles)
            processed = len(context.articles)
            stored = context.get("stored_count", 0) or 0
            errors_list.extend(
                f"{e.stage}: {e.message}" for e in context.errors
            )

        # تحديث الإحصائيات
        channel.config.stats.total_runs += 1
        channel.config.stats.total_fetched += len(articles)
        channel.config.stats.total_processed += processed
        channel.config.stats.total_stored += stored
        channel.config.stats.last_run_at = utc_now()
        channel.config.stats.last_run_status = "success" if not errors_list else "partial"
        if errors_list:
            channel.config.stats.failed_runs += 1
        else:
            channel.config.stats.successful_runs += 1

        ChannelRegistry.update_stats(channel_id)

        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "trigger_channel: id=%s run=%s fetched=%d processed=%d stored=%d %.1fms",
            channel_id, run_id, len(articles), processed, stored, duration_ms,
        )

        return TriggerResponse(
            channel_id=channel_id,
            run_id=run_id,
            status="success" if not errors_list else "partial",
            message="تمت المعالجة بنجاح" if not errors_list else f"اكتملت مع {len(errors_list)} خطأ",
            fetched=len(articles),
            processed=processed,
            stored=stored,
            duration_ms=round(duration_ms, 2),
            errors=errors_list[:10],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("trigger_channel: فشل القناة %s — %s", channel_id, exc, exc_info=True)
        channel.config.stats.failed_runs += 1
        channel.config.stats.last_error = str(exc)[:500]
        ChannelRegistry.update_status(channel_id, ChannelStatus.ERROR, actor="trigger")
        ChannelRegistry.update_stats(channel_id)
        raise HTTPException(status_code=500, detail=f"خطأ في تشغيل Pipeline: {exc}")


# ─────────────────────────────────────────────
# GET /channels/{channel_id}/status
# ─────────────────────────────────────────────

@router.get("/{channel_id}/status", response_model=StatusResponse)
async def get_channel_status(channel_id: str):
    """استرجاع حالة القناة وإحصائياتها التفصيلية."""
    channel = ChannelRegistry.get(channel_id)
    if channel:
        stats = channel.config.stats
        return StatusResponse(
            channel_id=channel_id,
            name=channel.config.name,
            status=channel.config.status.value,
            last_run=stats.last_run_at.isoformat() if stats.last_run_at else (
                channel.last_run.isoformat() if channel.last_run else None
            ),
            total_runs=stats.total_runs,
            total_fetched=stats.total_fetched,
            total_processed=stats.total_processed,
            total_stored=stats.total_stored,
            successful_runs=stats.successful_runs,
            failed_runs=stats.failed_runs,
            last_error=stats.last_error,
        )

    for cfg in ChannelRegistry.list_from_db():
        if cfg.id == channel_id:
            stats = cfg.stats
            return StatusResponse(
                channel_id=channel_id,
                name=cfg.name,
                status=cfg.status.value,
                last_run=stats.last_run_at.isoformat() if stats.last_run_at else None,
                total_runs=stats.total_runs,
                total_fetched=stats.total_fetched,
                total_processed=stats.total_processed,
                total_stored=stats.total_stored,
                successful_runs=stats.successful_runs,
                failed_runs=stats.failed_runs,
                last_error=stats.last_error,
            )

    raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")


# ─────────────────────────────────────────────
# GET /channels/{channel_id}/audit
# ─────────────────────────────────────────────

@router.get("/{channel_id}/audit")
async def get_channel_audit(
    channel_id: str,
    limit: int = Query(default=50, ge=1, le=500),
):
    """استرجاع سجل audit للقناة."""
    # التحقق من وجود القناة
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        found = any(cfg.id == channel_id for cfg in ChannelRegistry.list_from_db())
        if not found:
            raise HTTPException(status_code=404, detail=f"القناة '{channel_id}' غير موجودة")

    audit_log = ChannelRegistry.get_audit_log(channel_id, limit=limit)
    return {
        "channel_id": channel_id,
        "total": len(audit_log),
        "events": audit_log,
    }
