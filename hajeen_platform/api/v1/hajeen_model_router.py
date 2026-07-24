"""
Hajeen Model v1 API Router — واجهة API للنموذج المحلي.

Routes:
  GET  /api/v1/model/health          — حالة النموذج
  GET  /api/v1/model/info            — معلومات النموذج
  POST /api/v1/model/chat            — محادثة
  POST /api/v1/model/complete        — استدلال كامل
  POST /api/v1/model/stream          — streaming (SSE)
  GET  /api/v1/model/ollama/status   — حالة Ollama
  POST /api/v1/model/ollama/pull     — تحميل نموذج
  GET  /api/v1/model/training/status — حالة التدريب
  POST /api/v1/model/training/build-dataset — بناء dataset
  POST /api/v1/model/training/simulate — محاكاة التدريب
  POST /api/v1/model/evaluate        — تقييم النموذج
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
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


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/health")
async def model_health():
    """فحص شامل لحالة النموذج."""
    try:
        from hajeen_model.hajeen_model_v1 import get_hajeen_model
        model = get_hajeen_model()
        health = await model.health()
        return {"ok": True, **health}
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
        "model": config.get("model", {}),
        "inference": config.get("inference", {}),
        "capabilities": config.get("capabilities", []),
        "system_prompt": config.get("system_prompt", ""),
    }


from brain.brain_v3 import BrainRequest, BrainResponse, RequestType, get_brain_v3

@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """محادثة مع Hajeen Model v1 (موجهة عبر HajeenBrainV3)."""
    brain = request.app.state.brain
    if brain is None:
        raise HTTPException(status_code=503, detail="HajeenBrainV3 not initialized")

    brain_request = BrainRequest(
        request_id=f"hajeen_model_chat_{uuid.uuid4().hex[:12]}",
        user_message=req.message,
        session_id=str(uuid.uuid4()), # New session for this specific model chat, or use req.session_id if available
        context={
            "history": req.history,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        },
        stream=False,
        max_tokens=req.max_tokens or 1024,
        temperature=req.temperature or 0.7,
        force_model=None, # Let Brain decide
        request_type=RequestType.CHAT,
    )

    try:
        brain_response: BrainResponse = await brain.process(brain_request)
        return {
            "ok": True,
            "content": brain_response.content,
            "provider": brain_response.model_used, # Using model_used as provider for now
            "is_mock": False,
            "model": brain_response.model_used,
            "usage": {
                "prompt_tokens": brain_response.trace.tokens_used, # Assuming trace has this
                "completion_tokens": brain_response.trace.tokens_used, # Assuming trace has this
                "total_tokens": brain_response.trace.tokens_used,
            },
            "latency_ms": brain_response.trace.total_latency_ms,
        }
    except Exception as e:
        logger.error("Hajeen Model v1 chat error via Brain: %s", e)
        raise HTTPException(status_code=500, detail=f"Hajeen Model v1 chat error: {str(e)}")


@router.post("/complete")
async def complete(req: CompleteRequest, request: Request):
    """استدلال كامل مع رسائل متعددة."""
    try:
        brain = request.app.state.brain
        if brain is None:
            raise HTTPException(status_code=503, detail="HajeenBrainV3 not initialized")

        user_message = " ".join([m.content for m in req.messages if m.role == "user"])
        
        brain_request = BrainRequest(
            request_id=f"hajeen_model_complete_{uuid.uuid4().hex[:12]}",
            user_message=user_message,
            session_id=str(uuid.uuid4()),
            context={
                "messages": [m.dict() for m in req.messages],
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
            },
            stream=False,
            max_tokens=req.max_tokens or 1024,
            temperature=req.temperature or 0.7,
            force_model=None,
            request_type=RequestType.GENERATION,
        )

        brain_response: BrainResponse = await brain.process(brain_request)
        return {
            "ok": True,
            "content": brain_response.content,
            "model": brain_response.model_used,
            "usage": {
                "prompt_tokens": brain_response.trace.tokens_used,
                "completion_tokens": brain_response.trace.tokens_used,
                "total_tokens": brain_response.trace.tokens_used,
            },
            "latency_ms": brain_response.trace.total_latency_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_chat(req: ChatRequest, request: Request):
    """Streaming response (Server-Sent Events) via HajeenBrainV3."""
    brain = request.app.state.brain
    if brain is None:
        raise HTTPException(status_code=503, detail="HajeenBrainV3 not initialized")

    stream_id = str(uuid.uuid4())
    brain_request = BrainRequest(
        request_id=stream_id,
        user_message=req.message,
        session_id=str(uuid.uuid4()),
        context={
            "history": req.history,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": True,
        },
        stream=True,
        max_tokens=req.max_tokens or 1024,
        temperature=req.temperature or 0.7,
        force_model=None,
        request_type=RequestType.CHAT,
    )

    async def generator():
        try:
            async for chunk in brain.stream(brain_request):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield f"data: {json.dumps({\'type\': \'token\', \'content\': \'\'}, ensure_ascii=False)}\n\n"
                        yield "data: {\"type\": \"done\"}\n\n"
                        break
                    try:
                        import ast
                        data_dict = ast.literal_eval(data_str)
                        if "content" in data_dict:
                            yield f"data: {json.dumps({\'type\': \'token\', \'content\': data_dict[\'content\']}, ensure_ascii=False)}\n\n"
                        elif "brain_decision" in data_dict:
                            yield f"data: {json.dumps({\'type\': \'meta\', \'brain_decision\': data_dict[\'brain_decision\']}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        logger.debug("Failed to parse stream chunk from Brain: %s", e)
                        yield f"data: {json.dumps({\'type\': \'token\', \'content\': data_str}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Hajeen Model v1 stream error via Brain: %s", e)
            yield f"data: {json.dumps({\'type\': \'error\', \'error\': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# ─── Ollama Management ────────────────────────────────────────────────────────


@router.get("/ollama/status")
async def ollama_status():
    """حالة خادم Ollama والنماذج المثبتة."""
    try:
        from hajeen_model.ollama_manager import get_ollama_manager
        manager = get_ollama_manager()
        return await manager.status_report()
    except Exception as e:
        return {"ollama_running": False, "error": str(e)}


@router.post("/ollama/pull")
async def ollama_pull(model_name: str = "qwen2.5:1.5b"):
    """تحميل نموذج من Ollama (يستغرق وقتاً)."""
    try:
        from hajeen_model.ollama_manager import get_ollama_manager
        manager = get_ollama_manager()
        if not await manager.is_running():
            raise HTTPException(status_code=503, detail="Ollama غير مشغّل. شغّل: ollama serve")
        success = await manager.pull_model(model_name)
        return {"ok": success, "model": model_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ollama/reset")
async def ollama_reset():
    """إعادة فحص اتصال Ollama."""
    from hajeen_model.hajeen_model_v1 import get_hajeen_model
    get_hajeen_model().reset_ollama_cache()
    return {"ok": True, "message": "سيتم إعادة فحص Ollama في الطلب القادم"}


# ─── Training Management ──────────────────────────────────────────────────────


@router.get("/training/status")
async def training_status():
    """حالة منظومة التدريب."""
    from hajeen_model.training_pipeline import TrainingPipeline, ExperimentConfig
    pipeline = TrainingPipeline()
    reqs = pipeline.check_requirements()
    checkpoints = pipeline.checkpoint_manager.list_checkpoints()
    return {
        "requirements": reqs,
        "can_train": reqs["can_train"],
        "blockers": reqs["blockers"],
        "checkpoints_count": len(checkpoints),
        "checkpoints": checkpoints[-3:] if checkpoints else [],
    }


@router.post("/training/build-dataset")
async def build_dataset(req: DatasetBuildRequest):
    """بناء Dataset التدريب من بيانات المنصة."""
    try:
        from hajeen_model.dataset_builder import DatasetBuilder
        builder = DatasetBuilder()
        n1 = builder.load_from_storage(req.storage_dir)
        n2 = builder.load_from_processed(req.processed_dir)
        n3 = builder.add_synthetic_examples(req.add_synthetic) if req.add_synthetic > 0 else 0

        dataset = builder.build()
        stats = builder.stats()
        result = builder.save(dataset, "hajeen_model/data/dataset.jsonl", format=req.output_format)

        return {
            "ok": True,
            "loaded": {"storage": n1, "processed": n2, "synthetic": n3},
            "stats": {
                "total": stats.total,
                "arabic": stats.arabic,
                "english": stats.english,
                "avg_input_len_words": round(stats.avg_input_len, 1),
                "avg_output_len_words": round(stats.avg_output_len, 1),
                "estimated_tokens": stats.total_tokens_estimate,
            },
            "saved": result,
            "ready_for_training": result["total"] >= 100,
            "note": f"تحتاج إلى {max(0, 1000 - result['total'])} مثال إضافي للتدريب الجيد",
        }
    except Exception as e:
        logger.error("Build dataset error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training/simulate")
async def simulate_training(req: TrainingRequest):
    """محاكاة التدريب (بدون GPU)."""
    try:
        from hajeen_model.training_pipeline import TrainingPipeline, ExperimentConfig
        config = ExperimentConfig(
            base_model=req.base_model,
            num_epochs=req.num_epochs,
            batch_size=req.batch_size,
            learning_rate=req.learning_rate,
        )
        pipeline = TrainingPipeline(config)
        result = pipeline.run_simulation()
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training/start")
async def start_training(req: TrainingRequest, background_tasks: BackgroundTasks):
    """
    بدء التدريب الفعلي (يتطلب GPU).
    يُشغّل في الخلفية.
    """
    from hajeen_model.training_pipeline import TrainingPipeline, ExperimentConfig
    config = ExperimentConfig(
        base_model=req.base_model,
        num_epochs=req.num_epochs,
        batch_size=req.batch_size,
        learning_rate=req.learning_rate,
    )
    pipeline = TrainingPipeline(config)
    reqs = pipeline.check_requirements()

    if not reqs["can_train"]:
        return {
            "ok": False,
            "experiment_id": config.experiment_id,
            "blockers": reqs["blockers"],
            "message": "لا يمكن التدريب في البيئة الحالية. للتدريب الحقيقي: استخدم /training/simulate",
        }

    background_tasks.add_task(pipeline.run_training)
    return {
        "ok": True,
        "experiment_id": config.experiment_id,
        "message": "التدريب بدأ في الخلفية",
        "check_logs": "hajeen_model/logs/",
        "check_checkpoints": "hajeen_model/checkpoints/",
    }


# ─── Evaluation ───────────────────────────────────────────────────────────────


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
    from hajeen_model.training_pipeline import CheckpointManager
    manager = CheckpointManager()
    return {
        "checkpoints": manager.list_checkpoints(),
        "best": manager.get_best_checkpoint(),
    }
