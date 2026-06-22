"""Section 7.7 — Embeddings Generation Endpoint."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class EmbedRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=100)
    model_name: Optional[str] = Field(default=None)
    normalize: bool = True


class EmbedResult(BaseModel):
    text_preview: str
    dimensions: int
    model_name: str
    latency_ms: float
    vector_preview: List[float]


class EmbedResponse(BaseModel):
    total: int
    model_name: str
    dimensions: int
    total_ms: float
    results: List[EmbedResult]


@router.post("/generate", response_model=EmbedResponse, summary="توليد Embeddings")
async def generate_embeddings(req: EmbedRequest):
    """توليد embeddings لمجموعة نصوص."""
    try:
        from core.embeddings.embedding_manager import get_embedding_manager
        manager = get_embedding_manager()
        t0 = time.perf_counter()
        results = await manager.embed_batch(
            req.texts, model_name=req.model_name
        )
        total_ms = (time.perf_counter() - t0) * 1000
        return EmbedResponse(
            total=len(results),
            model_name=results[0].model_name if results else "",
            dimensions=results[0].dimensions if results else 0,
            total_ms=round(total_ms, 2),
            results=[
                EmbedResult(
                    text_preview=r.text[:80],
                    dimensions=r.dimensions,
                    model_name=r.model_name,
                    latency_ms=round(r.latency_ms, 3),
                    vector_preview=r.vector[:5],
                )
                for r in results
            ],
        )
    except Exception as exc:
        logger.error(f"Embedding error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/models", summary="قائمة النماذج المتاحة")
async def list_models():
    """قائمة نماذج الـ embedding المسجّلة."""
    from core.embeddings.embedding_registry import EmbeddingRegistry
    return {"models": EmbeddingRegistry.list_models()}


@router.get("/health", summary="فحص صحة Embedding Engine")
async def embedding_health():
    """فحص صحة Embedding Manager."""
    from core.embeddings.embedding_manager import get_embedding_manager
    manager = get_embedding_manager()
    return await manager.health_check()
