from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from .embedding_cache import EmbeddingCache
from .embedding_models import EmbeddingModelLoader

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    """Primary interface for generating vector embeddings."""

    _instance: Optional["EmbeddingEngine"] = None

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_size: int = 10_000,
        normalize: bool = True,
    ) -> None:
        self.model_name = model_name
        self.normalize = normalize
        self._loader = EmbeddingModelLoader()
        self._cache = EmbeddingCache(max_size=cache_size)
        self._model: Optional[Any] = None

    @classmethod
    def get_instance(cls, **kwargs: Any) -> "EmbeddingEngine":
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    def load(self) -> None:
        if self._model is None:
            logger.info("Loading embedding model: %s", self.model_name)
            self._model = self._loader.load(self.model_name)
            logger.info("Embedding model loaded")

    def embed(self, text: str) -> List[float]:
        self.load()
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        vec = self._loader.encode(self._model, [text], normalize=self.normalize)[0]
        self._cache.put(text, vec)
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        self.load()
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        results: List[Optional[List[float]]] = [None] * len(texts)

        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            vectors = self._loader.encode(self._model, uncached_texts, normalize=self.normalize)
            for idx, vec in zip(uncached_indices, vectors):
                results[idx] = vec
                self._cache.put(texts[idx], vec)

        return [r for r in results if r is not None]

    async def aembed(self, text: str) -> List[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_batch, texts)

    def dimensions(self) -> int:
        self.load()
        return self._loader.get_dimensions(self._model)

    def cache_stats(self) -> dict:
        return self._cache.stats()
