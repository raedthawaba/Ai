from __future__ import annotations

import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.model.model_registry import ModelRegistry

router = APIRouter()
_registry = ModelRegistry()


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "hajeen"
    display_name: str
    backend: str
    context_length: int


class ModelsListResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


@router.get("/models", response_model=ModelsListResponse, summary="List Available Models")
async def list_models(request: Request) -> ModelsListResponse:
    created_ts = int(time.time())
    models = _registry.list_models()
    return ModelsListResponse(
        data=[
            ModelInfo(
                id=m["model_id"],
                created=created_ts,
                display_name=m.get("display_name", m["model_id"]),
                backend=str(m.get("backend", "unknown")),
                context_length=m.get("context_length", 4096),
            )
            for m in models
        ]
    )


@router.get("/models/{model_id}", response_model=ModelInfo, summary="Get Model Info")
async def get_model(model_id: str) -> ModelInfo:
    cfg = _registry.get(model_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return ModelInfo(
        id=cfg.model_id,
        created=int(time.time()),
        display_name=cfg.display_name or cfg.model_id,
        backend=str(cfg.backend),
        context_length=cfg.context_length,
    )
