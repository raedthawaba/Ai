from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.utils.gpu_utils import GPUUtils

router = APIRouter()


class AIHealthResponse(BaseModel):
    status: str
    timestamp: float
    llm: Dict[str, Any]
    embeddings: Dict[str, Any]
    gpu: Dict[str, Any]
    uptime_seconds: float


_START_TIME = time.time()


@router.get("/health", response_model=AIHealthResponse, summary="AI System Health")
async def ai_health(request: Request) -> AIHealthResponse:
    llm = getattr(request.app.state, "llm_manager", None)
    embed_engine = getattr(request.app.state, "embedding_engine", None)

    llm_status = {
        "ready": llm is not None and getattr(llm, "is_ready", lambda: False)(),
        "provider": getattr(llm, "active_provider", "unknown") if llm else "not_loaded",
    }

    embed_status = {
        "ready": embed_engine is not None,
        "model": getattr(embed_engine, "model_name", "not_loaded") if embed_engine else "not_loaded",
    }

    gpu_info = GPUUtils.summary()
    overall = "healthy" if llm_status["ready"] else "degraded"

    return AIHealthResponse(
        status=overall,
        timestamp=time.time(),
        llm=llm_status,
        embeddings=embed_status,
        gpu=gpu_info,
        uptime_seconds=round(time.time() - _START_TIME, 2),
    )
