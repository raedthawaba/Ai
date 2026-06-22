"""API v1 Router — يجمع جميع routers الفرعية."""
from __future__ import annotations

from fastapi import APIRouter

from api.v1.channels.router import router as channels_router

router = APIRouter()

router.include_router(channels_router, prefix="/channels", tags=["Channels"])


@router.get("/health", tags=["Health"])
async def v1_health():
    return {"status": "ok", "version": "1.0"}


@router.get("/ping", tags=["Health"])
async def v1_ping():
    return {"message": "pong"}
