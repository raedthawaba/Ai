from __future__ import annotations

import time
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.embedding_service import EmbeddingService

router = APIRouter()
_svc = EmbeddingService()


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]] = Field(..., description="Text or list of texts to embed")
    model: Optional[str] = None
    encoding_format: str = Field(default="float", pattern="^(float|base64)$")


class EmbeddingObject(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    model: str
    data: List[EmbeddingObject]
    usage: dict
    latency_ms: float


@router.post("/embeddings", response_model=EmbeddingResponse, summary="Generate Embeddings")
async def create_embeddings(body: EmbeddingRequest) -> EmbeddingResponse:
    texts = [body.input] if isinstance(body.input, str) else body.input

    if not texts:
        raise HTTPException(status_code=400, detail="Input must not be empty")
    if len(texts) > 512:
        raise HTTPException(status_code=400, detail="Maximum 512 texts per request")

    result = await _svc.embed_batch(texts, model=body.model)
    vectors = result["embeddings"]

    return EmbeddingResponse(
        model=result["model"],
        data=[EmbeddingObject(embedding=vec, index=i) for i, vec in enumerate(vectors)],
        usage=result.get("usage", {"total_tokens": len(texts)}),
        latency_ms=result["latency_ms"],
    )
