"""Phase 8.7 + 9.6 — AI API Router: endpoints للذكاء الاصطناعي."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.v1.ai.chat import router as chat_router
from api.v1.ai.completion import router as completion_router
from api.v1.ai.embeddings import router as embeddings_router
from api.v1.ai.rerank import router as rerank_router
from api.v1.ai.models import router as models_router
from api.v1.ai.health import router as health_router
from hajeen_platform.hajeen_model.evaluation.evaluation_framework import EvaluationFramework

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Phase 9.6: Mount sub-routers ──────────────────────────────────────────────
router.include_router(chat_router, tags=["Chat"])
router.include_router(completion_router, tags=["Completion"])
router.include_router(embeddings_router, tags=["Embeddings"])
router.include_router(rerank_router, tags=["Rerank"])
router.include_router(models_router, tags=["Models"])
router.include_router(health_router, tags=["Health"])


# ── Request/Response Schemas ──────────────────────────────────────────────────

class MessageSchema(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str = Field(..., min_length=1)


class ChatRequestSchema(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    language: str = "ar"
    use_rag: bool = True
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)
    model: Optional[str] = None
    top_k: int = Field(5, ge=1, le=20)


class CompletionRequestSchema(BaseModel):
    messages: List[MessageSchema] = Field(..., min_items=1)
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=1, le=4096)
    stream: bool = False
    session_id: Optional[str] = None


class RAGQuerySchema(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(5, ge=1, le=20)
    language: str = "ar"
    use_llm: bool = True
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=2048)


# ── Dependency: Chat Service ───────────────────────────────────────────────────

def get_chat_service_dep():
    from services.chat.chat_service import get_chat_service
    return get_chat_service()


def get_inference_engine_dep():
    from core.inference_engine.engine import get_inference_engine
    return get_inference_engine()


# ── POST /chat ─────────────────────────────────────────────────────────────────

@router.post("/chat", summary="محادثة AI مع RAG", tags=["AI"])
async def chat(
    body: ChatRequestSchema,
    request: Request,
) -> Dict[str, Any]:
    """
    محادثة كاملة مع دعم RAG.

    - استرجاع دلالي تلقائي
    - إدارة جلسة المحادثة
    - حقن المصادر
    - دعم عربي/إنجليزي
    """
    from services.chat.chat_service import ChatRequest, get_chat_service

    chat_service = get_chat_service()

    # ربط RAG Pipeline من app state إن وُجد
    if not chat_service._rag:
        rag = getattr(request.app.state, "rag_pipeline", None)
        if rag:
            chat_service.set_rag_pipeline(rag)

    chat_request = ChatRequest(
        message=body.message,
        session_id=body.session_id,
        language=body.language,
        use_rag=body.use_rag,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        model=body.model,
        top_k=body.top_k,
    )

    try:
        response = await chat_service.chat(chat_request)
        return {
            "success": True,
            **response.to_dict(),
        }
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


# ── POST /chat/stream ──────────────────────────────────────────────────────────

@router.post("/chat/stream", summary="محادثة AI مع Streaming", tags=["AI"])
async def chat_stream(
    body: ChatRequestSchema,
    request: Request,
) -> StreamingResponse:
    """
    محادثة مع Streaming SSE.

    يُرجع tokens تدريجياً بتنسيق Server-Sent Events.
    """
    from services.chat.chat_service import ChatRequest, get_chat_service

    chat_service = get_chat_service()
    if not chat_service._rag:
        rag = getattr(request.app.state, "rag_pipeline", None)
        if rag:
            chat_service.set_rag_pipeline(rag)

    chat_request = ChatRequest(
        message=body.message,
        session_id=body.session_id,
        language=body.language,
        use_rag=body.use_rag,
        stream=True,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        model=body.model,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in chat_service.stream_chat(chat_request):
                data = json.dumps({
                    "type": event.event_type,
                    "data": event.data,
                    "index": event.chunk_index,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

                if event.event_type in ("done", "error"):
                    break
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'error', 'data': 'cancelled'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── POST /completion ───────────────────────────────────────────────────────────

@router.post("/completion", summary="LLM Completion مباشر", tags=["AI"])
async def completion(body: CompletionRequestSchema) -> Dict[str, Any]:
    """
    LLM Completion مباشر بدون RAG.

    يقبل قائمة messages ويرجع استجابة كاملة.
    """
    from core.inference_engine.engine import get_inference_engine

    engine = get_inference_engine()

    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        processed = await engine.infer(
            messages=messages,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            session_id=body.session_id,
        )
        return {
            "success": True,
            "response": processed.cleaned_content,
            "model": processed.model,
            "provider": processed.provider,
            "usage": {
                "prompt_tokens": processed.prompt_tokens,
                "completion_tokens": processed.completion_tokens,
                "total_tokens": processed.total_tokens,
            },
            "latency_ms": round(processed.latency_ms, 2),
        }
    except Exception as e:
        logger.error("Completion error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /rag/query ────────────────────────────────────────────────────────────

@router.post("/rag/query", summary="RAG Query مع LLM", tags=["AI", "RAG"])
async def rag_query(
    body: RAGQuerySchema,
    request: Request,
) -> Dict[str, Any]:
    """
    استعلام RAG كامل: Retrieval + Prompt Building + LLM inference.
    """
    rag_pipeline = getattr(request.app.state, "rag_pipeline", None)
    if not rag_pipeline:
        raise HTTPException(503, "RAG pipeline not initialized")

    try:
        from services.rag.rag_pipeline import RAGRequest

        rag_req = RAGRequest(
            query=body.query,
            top_k=body.top_k,
            language=body.language,
        )
        rag_result = await rag_pipeline.run(rag_req)
        result_dict = rag_result.to_dict()

        if body.use_llm:
            # إرسال الـ prompt الجاهز للـ LLM
            from core.inference_engine.engine import get_inference_engine
            from core.llm.base import LLMMessage

            engine = get_inference_engine()
            built_prompt = result_dict.get("prompt", body.query)
            processed = await engine.infer(
                messages=[{"role": "user", "content": built_prompt}],
                temperature=body.temperature or 0.7,
                max_tokens=body.max_tokens or 1024,
            )
            result_dict["llm_response"] = processed.cleaned_content
            result_dict["model"] = processed.model
            result_dict["tokens_used"] = processed.total_tokens

        return {"success": True, **result_dict}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("RAG query error: %s", e)
        raise HTTPException(500, f"RAG error: {str(e)}")


# ── GET /models ────────────────────────────────────────────────────────────────

@router.get("/models", summary="النماذج المتاحة", tags=["AI"])
async def list_models() -> Dict[str, Any]:
    """
    قائمة النماذج والمزودين المتاحين.
    """
    from core.llm.llm_manager import get_llm_manager
    from core.llm.provider_registry import ProviderRegistry

    manager = get_llm_manager()
    try:
        if not manager._initialized:
            await manager.initialize()
        available_models = await manager.get_available_models()
        health = await manager.health_check_all()
    except Exception as e:
        available_models = {}
        health = {}
        logger.warning("Models listing error: %s", e)

    ProviderRegistry.auto_register_defaults()

    return {
        "active_provider": manager.settings.provider,
        "active_model": manager.settings.model,
        "registered_providers": ProviderRegistry.list_providers(),
        "loaded_providers": available_models,
        "health": health,
    }


# ── GET /chat/sessions/{session_id} ───────────────────────────────────────────

@router.get("/chat/sessions/{session_id}", summary="معلومات جلسة المحادثة", tags=["AI"])
async def get_session(session_id: str) -> Dict[str, Any]:
    """الحصول على معلومات جلسة محادثة."""
    from services.chat.chat_service import get_chat_service

    chat_service = get_chat_service()
    info = chat_service.get_session_info(session_id)
    if not info:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return info


# ── POST /chat/sessions/{session_id}/clear ────────────────────────────────────

@router.post("/chat/sessions/{session_id}/clear", summary="مسح جلسة محادثة", tags=["AI"])
async def clear_session(session_id: str) -> Dict[str, Any]:
    """مسح سجل جلسة محادثة."""
    from services.memory.session_manager import get_session_manager

    manager = get_session_manager()
    deleted = manager.delete_session(session_id)
    return {
        "deleted": deleted,
        "session_id": session_id,
        "message": "Session cleared" if deleted else "Session not found",
    }


# ── GET /ai/stats ──────────────────────────────────────────────────────────────

@router.get("/stats", summary="إحصائيات AI Engine", tags=["AI"])
async def ai_stats() -> Dict[str, Any]:
    """إحصائيات شاملة لمحرك الـ AI."""
    from core.inference_engine.engine import get_inference_engine
    from services.memory.session_manager import get_session_manager
    from services.chat.chat_service import get_chat_service

    engine = get_inference_engine()
    session_mgr = get_session_manager()

    stats = engine.get_stats()
    session_stats = session_mgr.get_stats()

    return {
        "inference": stats,
        "sessions": session_stats,
        "phase": "8 — LLM Inference + AI Runtime",
    }

@router.post("/evaluate", summary="تشغيل إطار التقييم", tags=["AI"])
async def evaluate_model() -> Dict[str, Any]:
    """
    تشغيل إطار التقييم التلقائي وإرجاع تقرير مفصل.
    """
    eval_framework = EvaluationFramework()
    report = await eval_framework.evaluate_and_save_report()
    return report

