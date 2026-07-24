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
    system_prompt: Optional[str] = None


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


from brain.brain_v3 import BrainRequest, BrainResponse, RequestType

@router.post("/completion", response_model=CompletionResponse, summary="Text Completion عبر HajeenBrainV3")
async def text_completion(request: Request, body: CompletionRequest) -> CompletionResponse:
    brain = request.app.state.brain
    if brain is None:
        raise HTTPException(status_code=503, detail="HajeenBrainV3 not initialized")

    brain_request = BrainRequest(
        request_id=f"cmpl-{uuid.uuid4().hex[:12]}",
        user_message=body.prompt,
        session_id=str(uuid.uuid4()), # Completion requests might not have a session_id
        context={
            "temperature": body.temperature,
            "max_tokens": body.max_tokens,
            "top_p": body.top_p,
            "stop_sequences": body.stop or [],
            "system_prompt": body.system_prompt,
        },
        stream=False,
        max_tokens=body.max_tokens or 2048,
        temperature=body.temperature or 0.7,
        force_model=body.model,
        request_type=RequestType.GENERATION,
    )

    try:
        brain_response: BrainResponse = await brain.process(brain_request)
        
        text_content = brain_response.content
        if body.echo:
            text_content = body.prompt + text_content

        return CompletionResponse(
            id=brain_response.request_id,
            model=brain_response.model_used,
            choices=[CompletionChoice(text=text_content, index=0, finish_reason="stop")],
            usage={
                "prompt_tokens": brain_response.trace.tokens_used, # Assuming trace has this
                "completion_tokens": brain_response.trace.tokens_used, # Assuming trace has this
                "total_tokens": brain_response.trace.tokens_used,
            },
            latency_ms=brain_response.trace.total_latency_ms,
        )
    except Exception as e:
        logger.error("Brain completion error: %s", e)
        raise HTTPException(status_code=500, detail=f"Brain completion error: {str(e)}")


@router.post("/completion/stream", summary="Streaming Text Completion عبر HajeenBrainV3")
async def stream_completion(request: Request, body: CompletionRequest) -> StreamingResponse:
    brain = request.app.state.brain
    if brain is None:
        raise HTTPException(status_code=503, detail="HajeenBrainV3 not initialized")

    stream_id = f"cmpl-stream-{uuid.uuid4().hex[:12]}"
    brain_request = BrainRequest(
        request_id=stream_id,
        user_message=body.prompt,
        session_id=str(uuid.uuid4()),
        context={
            "temperature": body.temperature,
            "max_tokens": body.max_tokens,
            "top_p": body.top_p,
            "stop_sequences": body.stop or [],
            "system_prompt": body.system_prompt,
            "stream": True,
        },
        stream=True,
        max_tokens=body.max_tokens or 2048,
        temperature=body.temperature or 0.7,
        force_model=body.model,
        request_type=RequestType.GENERATION,
    )

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in brain.stream(brain_request):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield f"data: {json.dumps({\'choices\': [{\'delta\': {\'content\': \'\'}, \'finish_reason\': \'stop\'}]})}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                    try:
                        import ast
                        data_dict = ast.literal_eval(data_str)
                        if "content" in data_dict:
                            yield f"data: {json.dumps({\'choices\': [{\'delta\': {\'content\': data_dict[\'content\']}}]})}\n\n"
                        elif "brain_decision" in data_dict:
                            yield f"data: {json.dumps({\'meta\': {\'brain_decision\': data_dict[\'brain_decision\']}})}\n\n"
                    except Exception as e:
                        logger.debug("Failed to parse stream chunk from Brain: %s", e)
                        yield f"data: {json.dumps({\'choices\': [{\'delta\': {\'content\': data_str}}]})}\n\n"
        except Exception as e:
            logger.error("Brain stream completion error: %s", e)
            yield f"data: {json.dumps({\'error\': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
