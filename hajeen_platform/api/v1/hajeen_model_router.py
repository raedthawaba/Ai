"""
Hajeen Model v1 API Router — واجهة API للنموذج المحلي.

القاعدة الصارمة:
- جميع طلبات AI تمر عبر HajeenBrainV3
- هذا الـ Router مجرد HTTP Adapter — لا منطق AI مستقل هنا
- لا يوجد LLM call مباشر خارج Brain

Routes:
  GET  /api/v1/model/health          — حالة النموذج
  GET  /api/v1/model/info            — معلومات النموذج
  POST /api/v1/model/chat            — محادثة (موجهة عبر HajeenBrainV3)
  POST /api/v1/model/complete        — استدلال كامل (عبر HajeenBrainV3)
  POST /api/v1/model/stream          — streaming (SSE) (عبر HajeenBrainV3)
  GET  /api/v1/model/ollama/status   — حالة Ollama
  POST /api/v1/model/ollama/pull     — تحميل نموذج
  GET  /api/v1/model/training/status — حالة التدريب
  POST /api/v1/model/training/build-dataset — بناء dataset
  POST /api/v1/model/training/simulate — محاكاة التدريب
  POST /api/v1/model/evaluate        — تقييم النموذج
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model", tags=["Hajeen Model v1"])


# ─── Request / Response Models ────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant | system")
    content: str = Field(..., description="محتوى الرسالة")


class ChatRequest(BaseModel):
    message: str = Field(..., description="رسالة المستخدم")
    history: Optional[List[Dict]] = Field(default=None, description="سجل المحادثة")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    stream: bool = Field(default=False)
    session_id: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)


class CompleteRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=1024)


class DatasetBuildRequest(BaseModel):
    storage_dir: str = Field(default="storage_data/gold")
    processed_dir: str = Field(default="data/processed/pipeline")
    add_synthetic: int = Field(default=50, ge=0, le=5000)
    output_format: str = Field(default="alpaca")


class TrainingRequest(BaseModel):
    base_model: str = Field(default="Qwen/Qwen2.5-1.5B")
    num_epochs: int = Field(default=3, ge=1, le=20)
    batch_size: int = Field(default=4)
    learning_rate: float = Field(default=2e-4)
    simulation: bool = Field(default=True, description="True=محاكاة, False=تدريب فعلي")


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _get_brain_from_request(request: Request):
    """الحصول على HajeenBrainV3 من app state."""
    brain = getattr(request.app.state, "brain", None)
    if brain is None:
        from brain.brain_v3 import get_brain_v3
        brain = await get_brain_v3()
    return brain


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/health")
async def model_health():
    """فحص شامل لحالة النموذج."""
    try:
        from brain.brain_v3 import get_brain_v3
        brain = await get_brain_v3()
        stats = brain.get_stats()
        return {
            "ok": True,
            "model": "Hajeen Model v1 (via HajeenBrainV3)",
            "brain_version": brain.VERSION,
            "memory_overview": stats.get("memory_overview", {}),
            "routing_stats": stats.get("routing_stats", {}),
        }
    except Exception as e:
        logger.error("Model health check failed: %s", e)
        return {"ok": False, "error": str(e), "model": "Hajeen Model v1"}


@router.get("/info")
async def model_info():
    """معلومات النموذج."""
    import yaml
    from pathlib import Path
    config_path = Path("hajeen_model/config/model_config.yaml")
    config = {}
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return {
        "model": config.get("model", {"name": "Hajeen Model v1", "version": "1.0"}),
        "inference": config.get("inference", {"runtime": "HajeenBrainV3"}),
        "capabilities": config.get("capabilities", ["arabic", "general", "rag"]),
        "system_prompt": config.get("system_prompt", ""),
        "runtime": "HajeenBrainV3 (Unified Runtime)",
    }


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """
    محادثة مع Hajeen Model v1.

    الضمان: الطلب يمر عبر HajeenBrainV3.process() كاملاً.
    لا يوجد LLM call مباشر هنا.
    """
    from brain.brain_v3 import BrainRequest, get_brain_v3

    brain = await _get_brain_from_request(request)

    brain_request = BrainRequest(
        request_id=f"hajeen_model_chat_{uuid.uuid4().hex[:12]}",
        user_message=req.message,
        session_id=req.session_id or str(uuid.uuid4()),
        context={
            "history": req.history or [],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        },
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        force_model=req.model,
    )

    t0 = time.perf_counter()
    try:
        response = await brain.process(brain_request)
        return {
            "ok": True,
            "response": response.content,
            "session_id": brain_request.session_id,
            "model_used": response.model_used,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "runtime": "HajeenBrainV3",
        }
    except Exception as e:
        logger.error("Model chat error: %s", e)
        raise HTTPException(status_code=500, detail=f"HajeenBrainV3 error: {e}")


@router.post("/complete")
async def complete(req: CompleteRequest, request: Request):
    """
    استدلال كامل عبر HajeenBrainV3.
    """
    from brain.brain_v3 import BrainRequest, get_brain_v3

    brain = await _get_brain_from_request(request)
    last_user = next(
        (m.content for m in reversed(req.messages) if m.role == "user"),
        ""
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in req.messages[:-1]
    ]

    brain_request = BrainRequest(
        request_id=f"complete_{uuid.uuid4().hex[:12]}",
        user_message=last_user,
        session_id=str(uuid.uuid4()),
        context={"history": history},
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )

    t0 = time.perf_counter()
    try:
        response = await brain.process(brain_request)
        return {
            "ok": True,
            "content": response.content,
            "model_used": response.model_used,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "runtime": "HajeenBrainV3",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_chat(req: ChatRequest, request: Request):
    """
    Streaming محادثة عبر HajeenBrainV3.stream().
    الضمان: كل chunk يمر عبر Brain — لا LLM مباشر.
    """
    from brain.brain_v3 import BrainRequest, get_brain_v3

    brain = await _get_brain_from_request(request)

    brain_request = BrainRequest(
        request_id=f"stream_{uuid.uuid4().hex[:12]}",
        user_message=req.message,
        session_id=req.session_id or str(uuid.uuid4()),
        context={
            "history": req.history or [],
            "stream": True,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        },
        stream=True,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        force_model=req.model,
    )

    async def event_generator():
        try:
            async for chunk in brain.stream(brain_request):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/ollama/status")
async def ollama_status():
    """حالة Ollama."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            data = resp.json()
            return {"ok": True, "models": data.get("models", []), "status": "running"}
    except Exception as e:
        return {"ok": False, "status": "unavailable", "error": str(e)}


@router.post("/ollama/pull")
async def ollama_pull(background_tasks: BackgroundTasks, model: str = "qwen2.5:7b"):
    """تحميل نموذج Ollama في الخلفية."""
    async def pull():
        try:
            import httpx
            async with httpx.AsyncClient(timeout=600.0) as client:
                await client.post(
                    "http://localhost:11434/api/pull",
                    json={"name": model}
                )
            logger.info("Ollama: تم تحميل النموذج %s", model)
        except Exception as e:
            logger.error("Ollama pull failed: %s", e)

    background_tasks.add_task(pull)
    return {"ok": True, "message": f"جاري تحميل {model} في الخلفية"}


@router.get("/training/status")
async def training_status():
    """حالة التدريب."""
    from pathlib import Path
    checkpoints = list(Path("hajeen_model/checkpoints").glob("*.bin")) if Path("hajeen_model/checkpoints").exists() else []
    return {
        "ok": True,
        "checkpoints": len(checkpoints),
        "training_active": False,
        "note": "يمكن بدء التدريب عبر /model/training/simulate",
    }


@router.post("/training/build-dataset")
async def build_dataset(req: DatasetBuildRequest):
    """بناء dataset للتدريب."""
    try:
        from hajeen_model.training_pipeline import DatasetBuilder
        builder = DatasetBuilder()
        result = await builder.build(
            storage_dir=req.storage_dir,
            add_synthetic=req.add_synthetic,
            output_format=req.output_format,
        )
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e), "note": "Dataset builder غير متاح في البيئة الحالية"}


@router.post("/training/simulate")
async def simulate_training(req: TrainingRequest, background_tasks: BackgroundTasks):
    """محاكاة التدريب."""
    try:
        from hajeen_model.training_pipeline import TrainingPipeline, TrainingConfig
        config = TrainingConfig(
            base_model=req.base_model,
            num_epochs=req.num_epochs,
            batch_size=req.batch_size,
            learning_rate=req.learning_rate,
        )
        pipeline = TrainingPipeline(config)
        background_tasks.add_task(pipeline.run_training)
        return {
            "ok": True,
            "experiment_id": config.experiment_id,
            "message": "التدريب بدأ في الخلفية",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/evaluate")
async def evaluate_model():
    """تقييم النموذج بأسئلة متنوعة."""
    try:
        from hajeen_model.training_pipeline import ModelEvaluator
        evaluator = ModelEvaluator()
        report = await evaluator.evaluate_with_ollama()
        return {"ok": True, **report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/checkpoints")
async def list_checkpoints():
    """قائمة نقاط الحفظ."""
    try:
        from hajeen_model.training_pipeline import CheckpointManager
        manager = CheckpointManager()
        return {
            "checkpoints": manager.list_checkpoints(),
            "best": manager.get_best_checkpoint(),
        }
    except Exception as e:
        return {"checkpoints": [], "best": None, "error": str(e)}
