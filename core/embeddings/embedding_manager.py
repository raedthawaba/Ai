"""Singleton Embedding Manager — نقطة الدخول الموحّدة لجميع عمليات الـ embedding."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from core.embeddings.base import BaseEmbeddingModel, EmbeddingConfig, EmbeddingResult
from core.embeddings.embedding_registry import EmbeddingRegistry

logger = logging.getLogger(__name__)

_MANAGER_INSTANCE: Optional["EmbeddingManager"] = None


class EmbeddingManager:
    """Singleton يدير نماذج الـ embedding مع caching للنماذج المُحمَّلة."""

    def __init__(self, default_model: str = "all-MiniLM-L6-v2"):
        self._default_model_name = default_model
        self._models: Dict[str, BaseEmbeddingModel] = {}
        self._default_config = EmbeddingConfig(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
        )
        self._lock = asyncio.Lock()

    def _get_or_create(
        self,
        model_name: Optional[str] = None,
        config: Optional[EmbeddingConfig] = None,
    ) -> BaseEmbeddingModel:
        name = model_name or self._default_model_name
        if name not in self._models:
            cfg = config or EmbeddingConfig(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
            self._models[name] = EmbeddingRegistry.create(name, cfg)
            logger.info(f"نموذج جديد أُنشئ: {name}")
        return self._models[name]

    @property
    def default_model(self) -> BaseEmbeddingModel:
        return self._get_or_create()

    @property
    def dimensions(self) -> int:
        return self.default_model.dimensions

    async def embed(
        self,
        text: str,
        chunk_id: Optional[str] = None,
        article_id: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> EmbeddingResult:
        """تضمين نص واحد."""
        model = self._get_or_create(model_name)
        return await model.embed(text, chunk_id=chunk_id, article_id=article_id)

    async def embed_batch(
        self,
        texts: List[str],
        chunk_ids: Optional[List[str]] = None,
        article_id: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> List[EmbeddingResult]:
        """تضمين دُفعة من النصوص بكفاءة."""
        if not texts:
            return []
        model = self._get_or_create(model_name)
        return await model.embed_batch(texts, chunk_ids=chunk_ids, article_id=article_id)

    async def embed_texts_to_vectors(
        self,
        texts: List[str],
        model_name: Optional[str] = None,
    ) -> List[List[float]]:
        """يُعيد vectors فقط بدون metadata إضافية."""
        results = await self.embed_batch(texts, model_name=model_name)
        return [r.vector for r in results]

    async def health_check(self) -> dict:
        t0 = time.perf_counter()
        ok = await self.default_model.health_check()
        ms = (time.perf_counter() - t0) * 1000
        return {
            "status": "ok" if ok else "error",
            "model": self._default_model_name,
            "dimensions": self.dimensions,
            "latency_ms": round(ms, 2),
            "loaded_models": list(self._models.keys()),
        }

    def loaded_models(self) -> List[str]:
        return [name for name, m in self._models.items() if m.is_loaded]


def get_embedding_manager() -> EmbeddingManager:
    """Singleton factory."""
    global _MANAGER_INSTANCE
    if _MANAGER_INSTANCE is None:
        _MANAGER_INSTANCE = EmbeddingManager()
    return _MANAGER_INSTANCE
