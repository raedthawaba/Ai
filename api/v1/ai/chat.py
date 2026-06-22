from __future__ import annotations

import time
import uuid
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.inference_engine import InferenceConfig
from core.memory.memory_manager import MemoryManager
from core.prompts.prompt_builder import PromptBuilder
from services.moderation_service import ModerationService

router = APIRouter()

_moderator = ModerationService()
_prompt_builder = PromptBuilder()


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


@router.post("/chat", response_model=ChatResponse, summary="AI Chat Completion")
async def chat_completion(request: Request, body: ChatRequest) -> ChatResponse:
    last_user = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )
    mod = _moderator.check(last_user)
    if mod.action == "block":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mod.reason)

    llm = getattr(request.app.state, "llm_manager", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialized")

    history = [{"role": m.role, "content": m.content} for m in body.messages[:-1]]
    prompt = _prompt_builder.build_chat(
        user_message=last_user,
        history=None,
        system_override=next(
            (m.content for m in body.messages if m.role == "system"), None
        ),
    )

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


@router.post("/chat/stream", summary="Streaming Chat Completion")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    last_user = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )
    llm = getattr(request.app.state, "llm_manager", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialized")

    prompt = _prompt_builder.build_chat(user_message=last_user)
    config = InferenceConfig(
        max_new_tokens=body.max_tokens,
        temperature=body.temperature,
        stream=True,
    )

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in llm.astream(prompt, config=config, model_id=body.model):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
