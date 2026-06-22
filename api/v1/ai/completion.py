from __future__ import annotations

import time
import uuid
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.inference_engine import InferenceConfig

router = APIRouter()


class CompletionRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32_000)
    model: Optional[str] = None
    max_tokens: int = Field(default=256, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9)
    stop: Optional[List[str]] = None
    stream: bool = False
    echo: bool = False


class CompletionChoice(BaseModel):
    text: str
    index: int
    finish_reason: str


class CompletionResponse(BaseModel):
    id: str
    object: str = "text_completion"
    model: str
    choices: List[CompletionChoice]
    usage: dict
    latency_ms: float


@router.post("/completion", response_model=CompletionResponse, summary="Text Completion")
async def text_completion(request: Request, body: CompletionRequest) -> CompletionResponse:
    llm = getattr(request.app.state, "llm_manager", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialized")

    config = InferenceConfig(
        max_new_tokens=body.max_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        stop_sequences=body.stop or [],
    )

    start = time.perf_counter()
    text = await llm.agenerate(body.prompt, config=config, model_id=body.model)
    latency = time.perf_counter() - start

    if body.echo:
        text = body.prompt + text

    prompt_tokens = max(1, len(body.prompt.split()))
    completion_tokens = max(1, len(text.split()))

    return CompletionResponse(
        id=f"cmpl-{uuid.uuid4().hex[:12]}",
        model=body.model or getattr(llm, "default_model", "hajeen-default"),
        choices=[CompletionChoice(text=text, index=0, finish_reason="stop")],
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        latency_ms=round(latency * 1000, 2),
    )


@router.post("/completion/stream", summary="Streaming Text Completion")
async def stream_completion(request: Request, body: CompletionRequest) -> StreamingResponse:
    llm = getattr(request.app.state, "llm_manager", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialized")

    config = InferenceConfig(
        max_new_tokens=body.max_tokens,
        temperature=body.temperature,
        stream=True,
    )

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in llm.astream(body.prompt, config=config, model_id=body.model):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
