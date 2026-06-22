from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.embeddings.embedding_engine import EmbeddingEngine

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service layer for embedding generation with usage tracking."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self._engine = EmbeddingEngine.get_instance(model_name=model_name)
        self._total_requests = 0
        self._total_texts = 0

    async def embed(self, text: str) -> Dict[str, Any]:
        start = time.perf_counter()
        vector = await self._engine.aembed(text)
        latency = time.perf_counter() - start
        self._total_requests += 1
        self._total_texts += 1
        return {
            "embedding": vector,
            "dimensions": len(vector),
            "model": self._engine.model_name,
            "latency_ms": round(latency * 1000, 2),
        }

    async def embed_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        vectors = await self._engine.aembed_batch(texts)
        latency = time.perf_counter() - start
        self._total_requests += 1
        self._total_texts += len(texts)
        return {
            "embeddings": vectors,
            "dimensions": len(vectors[0]) if vectors else 0,
            "count": len(vectors),
            "model": self._engine.model_name,
            "latency_ms": round(latency * 1000, 2),
            "usage": {"total_tokens": sum(max(1, len(t.split())) for t in texts)},
        }

    def stats(self) -> Dict:
        return {
            "total_requests": self._total_requests,
            "total_texts_embedded": self._total_texts,
            "model": self._engine.model_name,
            "cache": self._engine.cache_stats(),
        }
