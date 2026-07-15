"""
Hajeen Brain API Router — واجهة REST لـ Hajeen Brain v2
=========================================================

Routes:
  POST /api/v1/brain/chat              — محادثة عبر Brain (المسار الكامل)
  POST /api/v1/brain/stream            — محادثة متدفقة (SSE)
  POST /api/v1/brain/analyze           — تحليل طلب بدون تنفيذ
  GET  /api/v1/brain/status            — حالة شاملة للـ Brain
  GET  /api/v1/brain/sovereignty       — تقرير الاستقلالية
  GET  /api/v1/brain/knowledge/{entity} — السياق المعرفي لكيان
  POST /api/v1/brain/weekly-analysis   — تشغيل التحليل الأسبوعي
  GET  /api/v1/brain/graph             — الرسم البياني للمعرفة
  GET  /api/v1/brain/performance       — أداء النماذج
  GET  /api/v1/brain/decisions         — قرارات Decision Engine الأخيرة
  GET  /api/v1/brain/reflections       — تقارير Self Reflection
  GET  /api/v1/brain/evolution         — اقتراحات Self Evolution
  GET  /api/v1/brain/policies          — حالة السياسات
  GET  /api/v1/brain/improvements      — التحسينات المقترحة
  POST /api/v1/brain/learn             — إضافة بيانات تدريب يدوياً
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["Hajeen Brain v2"])


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
    from brain import get_brain as _get
    return await _get()


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/chat")
async def brain_chat(req: BrainChatRequest):
    """
    المسار الكامل لـ Hajeen Brain:
    Policy → Goal → Decompose → Plan → Decide → Execute → Distill → Reflect
    """
    from brain import BrainRequest, get_brain as _get_brain
    brain = await _get_brain()

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
    """محادثة متدفقة (Server-Sent Events) عبر Brain."""
    from brain import BrainRequest, get_brain as _get_brain
    brain = await _get_brain()

    brain_req = BrainRequest(
        request_id=str(uuid.uuid4()),
        user_message=req.message,
        session_id=req.session_id,
        stream=True,
        max_tokens=req.max_tokens,
        force_model=req.force_model,
    )

    return StreamingResponse(
        brain.stream(brain_req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyze")
async def analyze_request(req: AnalyzeRequest):
    """تحليل الطلب عبر Goal Manager بدون تنفيذ فعلي."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()

    goal = await brain.goal_manager.analyze(req.message, context={"session_id": req.session_id})
    plan = await brain.task_decomposer.decompose(goal)
    graph = await brain.graph_planner.build_graph(plan)

    return {
        "ok": True,
        "goal": goal.to_dict(),
        "plan": plan.to_dict(),
        "graph": graph.to_dict(),
        "visualization": brain.graph_planner.visualize(graph),
    }


@router.get("/status")
async def brain_status():
    """حالة شاملة لـ Hajeen Brain."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    return {"ok": True, "brain": brain.get_status()}


@router.get("/sovereignty")
async def sovereignty_report():
    """تقرير الاستقلالية — مدى اعتماد Hajeen على النماذج الخارجية."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    report = brain.get_sovereignty_report()
    snapshot = brain.sovereignty.take_snapshot()
    return {
        "ok": True,
        "sovereignty": report,
        "snapshot": snapshot.to_dict(),
    }


@router.get("/knowledge/{entity}")
async def knowledge_context(entity: str):
    """السياق المعرفي لكيان في الرسم البياني للمعرفة."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    ctx = brain.get_knowledge_context(entity)
    return {"ok": True, "entity": entity, "context": ctx}


@router.get("/graph")
async def knowledge_graph_stats():
    """إحصائيات الرسم البياني للمعرفة."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    return {
        "ok": True,
        "stats": brain.knowledge_graph.get_stats(),
        "search_example": brain.knowledge_graph.search_nodes("Hajeen"),
    }


@router.post("/weekly-analysis")
async def weekly_analysis(background_tasks: BackgroundTasks):
    """تشغيل التحليل الأسبوعي — يقترح تحسينات وتطورات."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()

    result = await brain.trigger_weekly_analysis()
    return {"ok": True, "analysis": result}


@router.get("/performance")
async def model_performance(
    by: str = Query(default="quality", description="quality | speed | success"),
):
    """أداء النماذج — ترتيب حسب المعيار المحدد."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    leaderboard = brain.performance_db.get_leaderboard(by=by)
    stats = brain.performance_db.get_statistics()
    return {
        "ok": True,
        "leaderboard": leaderboard,
        "statistics": stats,
        "ranked_by": by,
    }


@router.get("/decisions")
async def recent_decisions(limit: int = Query(default=10, ge=1, le=50)):
    """آخر قرارات Decision Engine."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    decisions = brain.decision_engine.get_recent_decisions(limit)
    stats = brain.decision_engine.get_stats()
    return {"ok": True, "decisions": decisions, "stats": stats}


@router.get("/reflections")
async def reflection_reports(limit: int = Query(default=10, ge=1, le=50)):
    """تقارير Self Reflection — تقييم ذاتي بعد كل تنفيذ."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    reports = brain.reflection.get_recent_reports(limit)
    scores = brain.reflection.get_average_scores()
    lessons = brain.reflection.get_aggregated_lessons()
    return {
        "ok": True,
        "reports": reports,
        "average_scores": scores,
        "top_lessons": lessons[:10],
    }


@router.get("/evolution")
async def evolution_proposals():
    """اقتراحات Self Evolution — تطوير ذاتي للنظام."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    summary = brain.evolution.get_proposals_summary()
    rules = brain.evolution.get_current_rules()
    return {"ok": True, "proposals": summary, "current_rules": rules}


@router.get("/policies")
async def policy_status():
    """حالة محرك السياسات."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    stats = brain.policy.get_stats()
    return {"ok": True, "policy_stats": stats}


@router.get("/improvements")
async def pending_improvements():
    """التحسينات المقترحة من Autonomous Improvement Engine."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    pending = [s.to_dict() for s in brain.improvement.get_pending_suggestions()]
    latest_report = brain.improvement.get_latest_report()
    stats = brain.improvement.get_stats()
    return {
        "ok": True,
        "pending_suggestions": pending,
        "latest_report": latest_report.to_dict() if latest_report else None,
        "stats": stats,
    }


@router.get("/distillation")
async def distillation_stats():
    """إحصائيات Knowledge Distillation Pipeline."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    stats = brain.distillation.get_stats()
    training_samples = len(brain.distillation.get_training_dataset())
    return {
        "ok": True,
        "distillation_stats": stats,
        "training_samples_ready": training_samples,
        "note": "هذه البيانات ستُستخدم لتدريب النموذج المحلي",
    }


@router.post("/learn")
async def add_training_data(req: LearnRequest):
    """إضافة بيانات تدريب يدوياً من قِبَل الإنسان."""
    from brain import get_brain as _get_brain
    from knowledge.knowledge_distillation import DistilledKnowledge
    import uuid, time

    brain = await _get_brain()
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
        "is_approved": knowledge.is_approved,
        "message": "تمت إضافة العيّنة لقاعدة بيانات التدريب",
    }


@router.get("/memory/{session_id}")
async def session_memory(session_id: str):
    """عرض ذاكرة الجلسة."""
    from brain import get_brain as _get_brain
    brain = await _get_brain()
    session = brain.memory.get_session(session_id)
    conversation = brain.memory.get_conversation(session_id)
    return {
        "ok": True,
        "session_id": session_id,
        "session_data": session.get_all()[-10:],
        "conversation_window": conversation.get_window(),
        "memory_overview": brain.memory.get_overview(),
    }
