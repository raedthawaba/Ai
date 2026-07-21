"""
Model Server — main entry point for the high-performance inference serving layer.
Manages multiple inference backends, request scheduling, and health reporting.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .serving.batching_engine import BatchingEngine
from .serving.load_balancer import LoadBalancer
from .serving.model_pool import ModelPool
from .serving.request_scheduler import RequestScheduler
from .serving.streaming_server import StreamingServer

logger = logging.getLogger(__name__)

MODEL_POOL: Optional[ModelPool] = None
BATCHING_ENGINE: Optional[BatchingEngine] = None
REQUEST_SCHEDULER: Optional[RequestScheduler] = None
LOAD_BALANCER: Optional[LoadBalancer] = None
STREAMING_SERVER: Optional[StreamingServer] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global MODEL_POOL, BATCHING_ENGINE, REQUEST_SCHEDULER, LOAD_BALANCER, STREAMING_SERVER

    logger.info("Initializing inference serving layer...")

    MODEL_POOL = ModelPool(
        max_models=int(os.environ.get("MAX_LOADED_MODELS", "4")),
        model_dir=os.environ.get("MODEL_CACHE_DIR", "/models"),
    )
    await MODEL_POOL.initialize()

    BATCHING_ENGINE = BatchingEngine(
        max_batch_size=int(os.environ.get("MAX_BATCH_SIZE", "32")),
        max_wait_ms=int(os.environ.get("BATCH_WAIT_MS", "50")),
        model_pool=MODEL_POOL,
    )
    await BATCHING_ENGINE.start()

    REQUEST_SCHEDULER = RequestScheduler(
        batching_engine=BATCHING_ENGINE,
        max_queue_size=int(os.environ.get("MAX_QUEUE_SIZE", "1000")),
    )
    await REQUEST_SCHEDULER.start()

    LOAD_BALANCER = LoadBalancer(model_pool=MODEL_POOL)

    STREAMING_SERVER = StreamingServer(model_pool=MODEL_POOL)

    logger.info("Inference serving layer ready")
    yield

    logger.info("Shutting down inference serving layer...")
    if REQUEST_SCHEDULER:
        await REQUEST_SCHEDULER.stop()
    if BATCHING_ENGINE:
        await BATCHING_ENGINE.stop()
    if MODEL_POOL:
        await MODEL_POOL.cleanup()


app = FastAPI(
    title="Hajeen Inference Server",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class GenerationRequest(BaseModel):
    model: str
    messages: Optional[List[Dict[str, str]]] = None
    prompt: Optional[str] = None
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    stream: bool = False
    stop: Optional[List[str]] = None
    request_id: Optional[str] = None


class GenerationResponse(BaseModel):
    id: str
    model: str
    content: str
    finish_reason: str
    usage: Dict[str, int]
    latency_ms: float


@app.get("/health")
async def health() -> Dict[str, Any]:
    pool_status = MODEL_POOL.status() if MODEL_POOL else {"status": "not_initialized"}
    scheduler_status = REQUEST_SCHEDULER.status() if REQUEST_SCHEDULER else {}
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "model_pool": pool_status,
        "scheduler": scheduler_status,
    }


@app.get("/ready")
async def ready() -> Dict[str, Any]:
    if not MODEL_POOL or not REQUEST_SCHEDULER:
        raise HTTPException(status_code=503, detail="Server not ready")
    return {"status": "ready"}


@app.post("/generate", response_model=GenerationResponse)
async def generate(request: GenerationRequest) -> Any:
    if not REQUEST_SCHEDULER:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    if request.stream:
        if not STREAMING_SERVER:
            raise HTTPException(status_code=503, detail="Streaming not available")

        async def event_stream() -> AsyncGenerator[str, None]:
            async for chunk in STREAMING_SERVER.stream(
                model=request.model,
                prompt=request.prompt or "",
                messages=request.messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    result = await REQUEST_SCHEDULER.submit(
        model=request.model,
        prompt=request.prompt or "",
        messages=request.messages,
        generation_config={
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop": request.stop,
        },
        request_id=request.request_id,
    )

    return GenerationResponse(**result)


@app.get("/models")
async def list_models() -> Dict[str, Any]:
    if not MODEL_POOL:
        return {"models": []}
    return {"models": MODEL_POOL.list_loaded()}


@app.post("/models/{model_name}/load")
async def load_model(model_name: str) -> Dict[str, Any]:
    if not MODEL_POOL:
        raise HTTPException(status_code=503, detail="Model pool not initialized")
    await MODEL_POOL.load(model_name)
    return {"status": "loaded", "model": model_name}


@app.post("/models/{model_name}/unload")
async def unload_model(model_name: str) -> Dict[str, Any]:
    if not MODEL_POOL:
        raise HTTPException(status_code=503, detail="Model pool not initialized")
    await MODEL_POOL.unload(model_name)
    return {"status": "unloaded", "model": model_name}


@app.get("/metrics")
async def metrics() -> Response:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    port = int(os.environ.get("MODEL_SERVER_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
