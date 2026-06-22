"""Base abstractions for embedding models."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EmbeddingConfig:
    """إعدادات نموذج الـ embedding."""
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimensions: int = 384
    batch_size: int = 32
    max_seq_length: int = 256
    normalize_embeddings: bool = True
    device: str = "cpu"
    cache_dir: Optional[str] = None
    show_progress: bool = False


@dataclass
class EmbeddingResult:
    """نتيجة عملية embedding واحدة."""
    text: str
    vector: List[float]
    model_name: str
    dimensions: int
    latency_ms: float
    token_count: int = 0
    cached: bool = False
    chunk_id: Optional[str] = None
    article_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "model_name": self.model_name,
            "dimensions": self.dimensions,
            "latency_ms": round(self.latency_ms, 3),
            "token_count": self.token_count,
            "cached": self.cached,
            "vector_preview": self.vector[:5],
        }


class BaseEmbeddingModel(ABC):
    """الواجهة المجردة لجميع نماذج الـ embedding."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._loaded = False

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def dimensions(self) -> int:
        return self.config.dimensions

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def load(self) -> None:
        """تحميل النموذج (lazy loading)."""
        ...

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    @abstractmethod
    def _encode_batch(self, texts: List[str]) -> List[List[float]]:
        """الترميز الداخلي (synchronous)."""
        ...

    async def embed(self, text: str, chunk_id: Optional[str] = None,
                    article_id: Optional[str] = None) -> EmbeddingResult:
        """تضمين نص واحد."""
        import asyncio
        self.ensure_loaded()
        t0 = time.perf_counter()
        vectors = await asyncio.to_thread(self._encode_batch, [text])
        ms = (time.perf_counter() - t0) * 1000
        token_count = len(text.split())
        return EmbeddingResult(
            text=text,
            vector=vectors[0],
            model_name=self.model_name,
            dimensions=self.dimensions,
            latency_ms=ms,
            token_count=token_count,
            chunk_id=chunk_id,
            article_id=article_id,
        )

    async def embed_batch(
        self,
        texts: List[str],
        chunk_ids: Optional[List[str]] = None,
        article_id: Optional[str] = None,
    ) -> List[EmbeddingResult]:
        """تضمين دُفعة من النصوص."""
        import asyncio
        if not texts:
            return []
        self.ensure_loaded()
        t0 = time.perf_counter()
        vectors = await asyncio.to_thread(self._encode_batch, texts)
        total_ms = (time.perf_counter() - t0) * 1000
        per_ms = total_ms / len(texts)
        results = []
        for i, (text, vec) in enumerate(zip(texts, vectors)):
            cid = chunk_ids[i] if chunk_ids else None
            results.append(EmbeddingResult(
                text=text,
                vector=vec,
                model_name=self.model_name,
                dimensions=self.dimensions,
                latency_ms=per_ms,
                token_count=len(text.split()),
                chunk_id=cid,
                article_id=article_id,
            ))
        return results

    async def health_check(self) -> bool:
        try:
            result = await self.embed("health check test")
            return len(result.vector) == self.dimensions
        except Exception:
            return False
