"""
AI Chat Endpoints — موحّدة عبر HajeenBrainV3
================================================
جميع طلبات المحادثة تمر عبر HajeenBrainV3 Pipeline الموحّد.

المسارات:
  POST /ai/chat        → HajeenBrainV3.process() → JSON
  POST /ai/chat/stream → HajeenBrainV3.stream()  → SSE
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.inference_engine import InferenceConfig
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
        raise HTTPException(status_code=503, detail="HajeenBrain not initialized")
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
    محادثة AI موحّدة عبر HajeenBrainV3 Pipeline.

    يمر الطلب بالتسلسل:
      Policy → Intent → Context → Reasoning → Decision → Execute → Memory
    """
    last_user = _extract_last_user(body.messages)

    # 1. Moderation (pre-brain safety check)
    mod = _moderator.check(last_user)
    if mod.action == "block":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mod.reason)

    # 2. Get unified Brain
    brain = _get_brain(request)

    # 3. Build BrainRequest
    try:
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
    except Exception as exc:
        # Fallback: direct LLM if BrainRequest schema differs
        logger = request.app.state.get("logger") or print
        logger(f"BrainRequest build failed: {exc}, falling back to direct LLM")
        return await _fallback_chat(request, body, last_user)

    # 4. Process through Brain V3 Pipeline
    start = time.perf_counter()
    try:
        brain_resp = await brain.process(brain_req)
        latency = time.perf_counter() - start

        response_text = getattr(brain_resp, "response", None) or getattr(brain_resp, "content", "")
        model_used = getattr(brain_resp, "model_used", body.model) or body.model or "hajeen-brain"

        prompt_tokens = sum(max(1, len(m.content.split())) for m in body.messages)
        completion_tokens = max(1, len(response_text.split()))

        return ChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            model=model_used,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=response_text),
                    finish_reason="stop",
                )
            ],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            latency_ms=round(latency * 1000, 2),
        )

    except Exception as exc:
        # Fallback on Brain failure
        logger = getattr(request.app.state, "logger", print)
        logger(f"Brain process failed: {exc}, falling back to direct LLM")
        return await _fallback_chat(request, body, last_user)


async def _fallback_chat(request: Request, body: ChatRequest, last_user: str) -> ChatResponse:
    """Fallback: direct LLM call when Brain is unavailable."""
    llm = getattr(request.app.state, "llm_manager", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialized")

    from core.prompts.prompt_builder import PromptBuilder
    pb = PromptBuilder()

    history = _build_history(body.messages)
    system = next((m.content for m in body.messages if m.role == "system"), None)
    prompt = pb.build_chat(user_message=last_user, history=history, system_override=system)

    config = InferenceConfig(
        max_new_tokens=body.max_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        stop_sequences=body.stop or [],
    )

    start = time.perf_counter()
    text = await llm.agenerate(prompt, config=config, model_id=body.model)
    latency = time.perf_counter() - start

    prompt_tokens = sum(max(1, len(m.content.split())) for m in body.messages)
    completion_tokens = max(1, len(text.split()))

    return ChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        model=body.model or getattr(llm, "default_model", "hajeen-default"),
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=text),
                finish_reason="stop",
            )
        ],
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        latency_ms=round(latency * 1000, 2),
    )


@router.post("/chat/stream", summary="Streaming Chat via Brain V3")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    محادثة متدفقة موحّدة عبر HajeenBrainV3.
    """
    brain = _get_brain(request)
    last_user = _extract_last_user(body.messages)

    try:
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

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for chunk in brain.stream(brain_req):
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as exc:
        # Fallback to direct streaming
        llm = getattr(request.app.state, "llm_manager", None)
        if llm is None:
            raise HTTPException(status_code=503, detail="LLM not initialized")

        from core.prompts.prompt_builder import PromptBuilder
        pb = PromptBuilder()
        prompt = pb.build_chat(user_message=last_user)
        config = InferenceConfig(max_new_tokens=body.max_tokens, temperature=body.temperature, stream=True)

        async def fallback_generator() -> AsyncIterator[str]:
            async for chunk in llm.astream(prompt, config=config, model_id=body.model):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(fallback_generator(), media_type="text/event-stream")
