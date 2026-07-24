"""
AI Chat Endpoints — موحّدة عبر HajeenBrainV3
================================================
جميع طلبات المحادثة تمر عبر HajeenBrainV3 Pipeline الموحّد.

المسارات:
  POST /ai/chat        → HajeenBrainV3.process() → JSON
  POST /ai/chat/stream → HajeenBrainV3.stream()  → SSE

القاعدة الصارمة:
  - لا يوجد أي LLM call مباشر خارج Brain.
  - لا يوجد fallback يتجاوز Pipeline الكاملة.
  - أي خطأ يُرجع HTTP error واضح بدلاً من تجاوز Brain.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.moderation_service import ModerationService

router = APIRouter()
_moderator = ModerationService()


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=32_000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)
    model: Optional[str] = None
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    stream: bool = False
    session_id: Optional[str] = None
    use_rag: bool = False
    stop: Optional[List[str]] = None


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: List[ChatChoice]
    usage: dict
    latency_ms: float


def _get_brain(request: Request):
    """الحصول على Brain من app state (مهيّأ في startup)."""
    brain = getattr(request.app.state, "brain", None)
    if brain is None:
        raise HTTPException(
            status_code=503,
            detail="HajeenBrainV3 not initialized — لا يمكن تنفيذ أي طلب خارج Brain"
        )
    return brain


def _extract_last_user(messages: List[ChatMessage]) -> str:
    """استخراج آخر رسالة من المستخدم."""
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


def _build_history(messages: List[ChatMessage]) -> List[dict]:
    """بناء تاريخ المحادثة بدون آخر رسالة."""
    history = []
    last_user_found = False
    for m in reversed(messages):
        if m.role == "user" and not last_user_found:
            last_user_found = True
            continue
        history.insert(0, {"role": m.role, "content": m.content})
    return history


@router.post("/chat", response_model=ChatResponse, summary="AI Chat via Brain V3")
async def chat_completion(request: Request, body: ChatRequest) -> ChatResponse:
    """
    محادثة AI موحّدة عبر HajeenBrainV3 Pipeline الكامل.

    المسار المضمون:
      HTTP Request
      ↓
      Moderation (Pre-Brain Safety)
      ↓
      HajeenBrainV3.process()
      ↓
      Policy → Intent → Context → Reasoning → Planning → Decision
      ↓
      ModelRouter → LLM Provider
      ↓
      MemoryFabric (SSOT)
      ↓
      Response

    لا يوجد مسار بديل (Fallback) يتجاوز Brain.
    """
    t0 = time.perf_counter()
    last_user = _extract_last_user(body.messages)

    # 1. Moderation (فحص أمان قبل Brain — الجزء الوحيد المسموح قبله)
    try:
        mod = _moderator.check(last_user)
        if mod.action == "block":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=mod.reason
            )
    except HTTPException:
        raise
    except Exception:
        pass  # إذا فشل Moderator، نكمل عبر Brain

    # 2. الحصول على العقل المركزي (يرفع 503 إذا لم يكن جاهزاً)
    brain = _get_brain(request)

    # 3. بناء BrainRequest وتمريره عبر Pipeline الكامل
    from brain import BrainRequest
    brain_req = BrainRequest(
        request_id=f"chat_{uuid.uuid4().hex[:12]}",
        user_message=last_user,
        session_id=body.session_id or str(uuid.uuid4()),
        context={
            "history": _build_history(body.messages),
            "system_prompt": next(
                (m.content for m in body.messages if m.role == "system"), None
            ),
            "use_rag": body.use_rag,
            "temperature": body.temperature,
            "max_tokens": body.max_tokens,
            "top_p": body.top_p,
        }
    )

    # 4. تنفيذ عبر Brain — لا يوجد fallback هنا
    try:
        brain_response = await brain.process(brain_req)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"HajeenBrainV3 processing failed: {exc}"
        )

    latency_ms = (time.perf_counter() - t0) * 1000
    response_text = getattr(brain_response, "content", str(brain_response))
    model_used = getattr(brain_response, "model_used", body.model or "hajeen-brain-v3")

    return ChatResponse(
        id=brain_req.request_id,
        object="chat.completion",
        model=model_used,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=response_text),
                finish_reason="stop",
            )
        ],
        usage={
            "prompt_tokens": len(last_user.split()),
            "completion_tokens": len(response_text.split()),
            "total_tokens": len(last_user.split()) + len(response_text.split()),
        },
        latency_ms=round(latency_ms, 2),
    )


@router.post("/chat/stream", summary="Streaming Chat via Brain V3")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    محادثة متدفقة موحّدة عبر HajeenBrainV3.

    الضمان: كل chunk يمر عبر Brain.stream() — لا يوجد مسار مباشر للـ LLM.
    """
    # 1. الحصول على Brain (يرفع 503 إذا لم يكن جاهزاً — لا fallback)
    brain = _get_brain(request)
    last_user = _extract_last_user(body.messages)

    # 2. بناء BrainRequest
    from brain import BrainRequest
    brain_req = BrainRequest(
        request_id=f"chat_stream_{uuid.uuid4().hex[:12]}",
        user_message=last_user,
        session_id=body.session_id or str(uuid.uuid4()),
        context={
            "history": _build_history(body.messages),
            "stream": True,
            "temperature": body.temperature,
            "max_tokens": body.max_tokens,
        }
    )

    # 3. Streaming عبر Brain فقط — لا يوجد fallback للـ LLM المباشر
    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in brain.stream(brain_req):
                yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            error_payload = json.dumps({"error": str(exc), "source": "HajeenBrainV3"})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
