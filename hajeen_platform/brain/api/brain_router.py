"""
Hajeen Brain API Router — واجهة REST لـ HajeenBrainV3
=====================================================
تم ترقية هذا الـ Router من Brain v2 إلى Adapter كامل لـ HajeenBrainV3.

القاعدة الصارمة:
- جميع الطلبات تمر عبر HajeenBrainV3.process() أو HajeenBrainV3.stream()
- لا يوجد أي منطق AI مستقل هنا
- هذا الـ Router مجرد Adapter بين HTTP وBrain

Routes:
  POST /api/v1/brain/chat              — محادثة عبر Brain (المسار الكامل)
  POST /api/v1/brain/stream            — محادثة متدفقة (SSE)
  POST /api/v1/brain/analyze           — تحليل طلب بدون تنفيذ
  GET  /api/v1/brain/status            — حالة شاملة للـ Brain
  GET  /api/v1/brain/sovereignty       — تقرير الاستقلالية
  GET  /api/v1/brain/knowledge/{entity} — السياق المعرفي لكيان
  GET  /api/v1/brain/performance       — أداء النماذج
  GET  /api/v1/brain/decisions         — قرارات Decision Engine الأخيرة
  GET  /api/v1/brain/reflections       — تقارير Self Reflection
  GET  /api/v1/brain/evolution         — اقتراحات Self Evolution
  GET  /api/v1/brain/policies          — حالة السياسات
  GET  /api/v1/brain/improvements      — التحسينات المقترحة
  POST /api/v1/brain/learn             — إضافة بيانات تدريب يدوياً
  GET  /api/v1/brain/memory/{session}  — ذاكرة الجلسة عبر MemoryFabric
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["Hajeen Brain v3"])


# ── Request / Response Models ──────────────────────────────────────────────


class BrainChatRequest(BaseModel):
    message: str = Field(..., description="رسالة المستخدم")
    session_id: str = Field(default="default", description="معرف الجلسة")
    user_id: Optional[str] = Field(default=None)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    force_model: Optional[str] = Field(default=None, description="إجبار نموذج معين")
    context: Dict[str, Any] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    message: str = Field(..., description="الطلب للتحليل")
    session_id: str = Field(default="default")


class LearnRequest(BaseModel):
    instruction: str = Field(..., description="تعليمة التدريب")
    output: str = Field(..., description="الإجابة المثالية")
    domain: str = Field(default="general")
    source: str = Field(default="human_curated")
    quality_score: float = Field(default=0.9, ge=0.0, le=1.0)


# ── Helpers ────────────────────────────────────────────────────────────────


async def _get_brain():
    """الحصول على HajeenBrainV3 Singleton."""
    from brain.brain_v3 import get_brain_v3
    return await get_brain_v3()


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/chat")
async def brain_chat(req: BrainChatRequest):
    """
    المسار الكامل لـ HajeenBrainV3:
    Policy → Intent → Context → Reasoning → Planning → Decision
    → ModelRouter → LLM → MemoryFabric → Reflection → Response
    """
    from brain.brain_v3 import BrainRequest, get_brain_v3
    brain = await get_brain_v3()

    brain_req = BrainRequest(
        request_id=str(uuid.uuid4()),
        user_message=req.message,
        session_id=req.session_id,
        user_id=req.user_id,
        context=req.context,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        force_model=req.force_model,
    )

    t0 = time.perf_counter()
    try:
        response = await brain.process(brain_req)
        return {
            "ok": True,
            "response": response.to_dict(),
            "processing_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        logger.error("brain_chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def brain_stream(req: BrainChatRequest):
    """محادثة متدفقة (Server-Sent Events) عبر HajeenBrainV3."""
    from brain.brain_v3 import BrainRequest, get_brain_v3
    brain = await get_brain_v3()

    brain_req = BrainRequest(
        request_id=str(uuid.uuid4()),
        user_message=req.message,
        session_id=req.session_id,
        user_id=req.user_id,
        context=req.context,
        stream=True,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        force_model=req.force_model,
    )

    async def event_generator():
        try:
            async for chunk in brain.stream(brain_req):
                payload = json.dumps({"content": chunk, "session_id": req.session_id})
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("brain_stream error: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/analyze")
async def brain_analyze(req: AnalyzeRequest):
    """تحليل طلب بدون تنفيذ كامل."""
    from brain.brain_v3 import BrainRequest, get_brain_v3
    brain = await get_brain_v3()

    return {
        "ok": True,
        "message": req.message,
        "session_id": req.session_id,
        "brain_version": brain.VERSION,
        "analysis": {
            "intent": "تحليل الطلب يتم عبر HajeenBrainV3 Pipeline",
            "pipeline": [
                "Policy", "Intent", "Context", "Reasoning",
                "Planning", "Decision", "ModelRouter", "MemoryFabric"
            ],
        },
    }


@router.get("/status")
async def brain_status():
    """حالة شاملة لـ HajeenBrainV3."""
    try:
        brain = await _get_brain()
        stats = brain.get_stats()
        return {
            "ok": True,
            "version": brain.VERSION,
            "runtime": "HajeenBrainV3",
            "is_unified": True,
            "stats": stats,
        }
    except Exception as e:
        logger.error("brain_status error: %s", e)
        return {
            "ok": False,
            "version": "3.0.0",
            "runtime": "HajeenBrainV3",
            "error": str(e),
        }


@router.get("/sovereignty")
async def brain_sovereignty():
    """تقرير استقلالية النموذج."""
    brain = await _get_brain()
    routing_stats = brain.model_router.get_routing_stats()
    total = routing_stats.get("total", 0)
    by_model = routing_stats.get("by_model", {})

    local_calls = sum(
        count for model, count in by_model.items()
        if "hajeen" in model.lower() or "local" in model.lower() or "ollama" in model.lower()
    )

    return {
        "ok": True,
        "total_requests": total,
        "local_requests": local_calls,
        "sovereignty_score": round(local_calls / max(total, 1), 3),
        "by_model": by_model,
        "runtime": "HajeenBrainV3",
    }


@router.get("/performance")
async def brain_performance():
    """أداء النماذج عبر ModelRouter."""
    brain = await _get_brain()
    return {
        "ok": True,
        "routing_stats": brain.model_router.get_routing_stats(),
        "runtime": "HajeenBrainV3",
    }


@router.get("/memory/{session_id}")
async def session_memory(session_id: str):
    """عرض ذاكرة الجلسة من MemoryFabric (مصدر الحقيقة الوحيد)."""
    brain = await _get_brain()
    try:
        conversation = brain.memory.get_conversation(session_id)
        session = brain.memory.get_session(session_id)
        return {
            "ok": True,
            "session_id": session_id,
            "source": "MemoryFabric",
            "conversation_window": conversation.get_window(),
            "session_data": session.get_all()[-10:],
            "memory_overview": brain.memory.get_overview(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn")
async def add_training_data(req: LearnRequest):
    """إضافة بيانات تدريب يدوياً."""
    from brain.brain_v3 import get_brain_v3
    brain = await get_brain_v3()

    try:
        knowledge = await brain.distillation.distill(
            source_model=f"human:{req.source}",
            query=req.instruction,
            response=req.output,
            task_type="human_curated",
            domain=req.domain,
        )
        return {
            "ok": True,
            "knowledge_id": knowledge.knowledge_id,
            "quality_score": knowledge.solution_quality,
            "message": "تمت إضافة العيّنة لقاعدة بيانات التدريب",
        }
    except Exception as e:
        # Brain قد لا يحتوي distillation في الإعداد الحالي
        return {
            "ok": False,
            "message": f"Knowledge distillation غير متاح حالياً: {e}",
            "note": "يمكن إضافة البيانات يدوياً عبر MemoryFabric",
        }
