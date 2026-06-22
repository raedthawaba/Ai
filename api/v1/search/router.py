"""Section 7.7 — Search & RAG API Endpoints."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

# ─── Request / Response models ───────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="نص الاستعلام")
    top_k: int = Field(default=10, ge=1, le=50, description="عدد النتائج")
    filter_metadata: Optional[Dict[str, Any]] = Field(default=None)
    rerank: bool = Field(default=True)

class SemanticSearchRequest(SearchRequest):
    model_name: Optional[str] = Field(default=None)

class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    language: str = Field(default="ar", pattern="^(ar|en|auto)$")
    max_context_tokens: int = Field(default=2000, ge=100, le=8000)
    filter_metadata: Optional[Dict[str, Any]] = None

class SearchHitOut(BaseModel):
    rank: int
    chunk_id: str
    article_id: str
    text: str
    score: float
    source_url: str = ""
    source_title: str = ""

class SearchResponseOut(BaseModel):
    query: str
    search_type: str
    total_found: int
    search_time_ms: float
    model_name: str
    hits: List[SearchHitOut]
    metadata: Dict[str, Any] = {}

class RAGResponseOut(BaseModel):
    query: str
    status: str
    total_ms: float
    num_citations: int
    context_chars: int
    citations: List[Dict[str, Any]]
    prompt_ready: str
    stage_timings: Dict[str, float] = {}
    metadata: Dict[str, Any] = {}


# ─── Dependency: الحصول على SearchEngine و RAGPipeline ────────────────────────

def _get_search_state():
    """يجلب search engine من app state."""
    from api.main import _search_state
    return _search_state


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/", response_model=SearchResponseOut, summary="بحث دلالي")
async def search(req: SearchRequest):
    """بحث دلالي في المحتوى المُخزَّن."""
    state = _get_search_state()
    engine = state.get("engine")
    if engine is None:
        raise HTTPException(status_code=503, detail="Search engine غير جاهز — يرجى فهرسة محتوى أولاً")
    try:
        response = await engine.search(
            query=req.query,
            top_k=req.top_k,
            filter_metadata=req.filter_metadata,
        )
        return SearchResponseOut(
            query=response.query,
            search_type=response.search_type,
            total_found=response.total_found,
            search_time_ms=response.search_time_ms,
            model_name=response.model_name,
            hits=[SearchHitOut(**h.to_dict(), text=h.text) for h in response.hits],
            metadata=response.metadata,
        )
    except Exception as exc:
        logger.error(f"Search error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/semantic", response_model=SearchResponseOut, summary="بحث دلالي متقدم")
async def semantic_search(req: SemanticSearchRequest):
    """بحث دلالي مع تحديد النموذج."""
    state = _get_search_state()
    engine = state.get("engine")
    if engine is None:
        raise HTTPException(status_code=503, detail="Search engine غير جاهز")
    try:
        response = await engine.search(
            query=req.query,
            top_k=req.top_k,
            filter_metadata=req.filter_metadata,
            search_type="semantic",
        )
        return SearchResponseOut(
            query=response.query,
            search_type=response.search_type,
            total_found=response.total_found,
            search_time_ms=response.search_time_ms,
            model_name=response.model_name,
            hits=[SearchHitOut(**h.to_dict(), text=h.text) for h in response.hits],
            metadata=response.metadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/rag", response_model=RAGResponseOut, summary="RAG Pipeline")
async def rag_search(req: RAGRequest):
    """
    تنفيذ RAG pipeline كامل:
    استعلام → استرجاع → بناء context → بناء prompt.
    """
    state = _get_search_state()
    rag_pipeline = state.get("rag_pipeline")
    if rag_pipeline is None:
        raise HTTPException(status_code=503, detail="RAG pipeline غير جاهز")
    try:
        from services.rag.rag_pipeline import RAGRequest as InternalRAGRequest
        internal_req = InternalRAGRequest(
            query=req.query,
            top_k=req.top_k,
            language=req.language,
            max_context_tokens=req.max_context_tokens,
            filter_metadata=req.filter_metadata,
        )
        rag_response = await rag_pipeline.run(internal_req)
        fd = rag_response.formatted
        return RAGResponseOut(
            query=req.query,
            status="ready_for_llm",
            total_ms=rag_response.total_ms,
            num_citations=len(fd.citations),
            context_chars=len(fd.context_used),
            citations=fd.citations,
            prompt_ready=fd.prompt_ready,
            stage_timings=rag_response.stage_timings,
            metadata=fd.metadata,
        )
    except Exception as exc:
        logger.error(f"RAG error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats", summary="إحصائيات البحث")
async def search_stats():
    """إحصائيات Vector Store والـ Search Engine."""
    state = _get_search_state()
    engine = state.get("engine")
    if engine is None:
        return {"status": "not_initialized", "index_size": 0}
    stats = engine.vector_store.stats()
    return {
        "status": "ok",
        "index_size": stats.total_vectors,
        "index_type": stats.index_type,
        "dimensions": stats.dimensions,
        "is_trained": stats.is_trained,
    }
