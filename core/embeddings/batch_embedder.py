from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BatchEmbedder:
    """Embed large text collections efficiently with configurable batch size."""

    def __init__(
        self,
        engine: Any,
        batch_size: int = 64,
        show_progress: bool = False,
    ) -> None:
        self.engine = engine
        self.batch_size = batch_size
        self.show_progress = show_progress

    def embed_documents(
        self,
        documents: List[Dict],
        text_field: str = "content",
    ) -> List[Dict]:
        texts = [doc.get(text_field, "") for doc in documents]
        vectors = self._embed_in_batches(texts)
        result = []
        for doc, vec in zip(documents, vectors):
            result.append({**doc, "embedding": vec})
        return result

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self._embed_in_batches(texts)

    async def aembed_texts(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_texts, texts)

    def _embed_in_batches(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        total = len(texts)
        for start in range(0, total, self.batch_size):
            batch = texts[start: start + self.batch_size]
            vecs = self.engine.embed_batch(batch)
            results.extend(vecs)
            if self.show_progress:
                done = min(start + self.batch_size, total)
                logger.info("Embedded %d/%d texts", done, total)
        return results

    def embed_with_metadata(
        self,
        texts: List[str],
        metadata: Optional[List[Dict]] = None,
    ) -> List[Tuple[List[float], Dict]]:
        vectors = self.embed_texts(texts)
        meta = metadata or [{} for _ in texts]
        return list(zip(vectors, meta))
