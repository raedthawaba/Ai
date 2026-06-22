from __future__ import annotations

import time
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.rag.reranker import CrossEncoderReranker
from services.rag.retriever import RetrievalResult

router = APIRouter()
_reranker = CrossEncoderReranker()


class RerankDocument(BaseModel):
    id: Optional[str] = None
    text: str


class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    documents: List[RerankDocument] = Field(..., min_length=1, max_length=100)
    top_k: Optional[int] = Field(default=None, ge=1)
    return_documents: bool = True


class RerankResult(BaseModel):
    index: int
    relevance_score: float
    document: Optional[RerankDocument] = None


class RerankResponse(BaseModel):
    results: List[RerankResult]
    model: str
    latency_ms: float


@router.post("/rerank", response_model=RerankResponse, summary="Rerank Documents")
async def rerank_documents(body: RerankRequest) -> RerankResponse:
    start = time.perf_counter()

    results_in = [
        RetrievalResult(
            doc_id=doc.id or str(i),
            content=doc.text,
            score=1.0,
        )
        for i, doc in enumerate(body.documents)
    ]

    reranked = _reranker.rerank(body.query, results_in, top_k=body.top_k)
    latency = time.perf_counter() - start

    output: List[RerankResult] = []
    for r in reranked:
        idx = int(r.doc_id) if r.doc_id.isdigit() else 0
        output.append(
            RerankResult(
                index=idx,
                relevance_score=round(r.score, 6),
                document=body.documents[idx] if body.return_documents else None,
            )
        )

    return RerankResponse(
        results=output,
        model="hajeen-reranker",
        latency_ms=round(latency * 1000, 2),
    )
