"""SentenceTransformer embedding model implementation."""
from __future__ import annotations

import logging
from typing import List, Optional

from .base import BaseEmbeddingModel, EmbeddingConfig

logger = logging.getLogger(__name__)


class SentenceTransformerModel(BaseEmbeddingModel):
    """نموذج sentence-transformers — يدعم all-MiniLM-L6-v2 وغيره."""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        super().__init__(config or EmbeddingConfig())
        self._model = None

    def load(self) -> None:
        """تحميل النموذج من HuggingFace (lazy)."""
        if self._loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"تحميل نموذج: {self.config.model_name}")
            self._model = SentenceTransformer(
                self.config.model_name,
                device=self.config.device,
                cache_folder=self.config.cache_dir,
            )
            self._model.max_seq_length = self.config.max_seq_length
            # تحديث الأبعاد الفعلية من النموذج
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim:
                self.config.dimensions = actual_dim
            self._loaded = True
            logger.info(f"النموذج جاهز — أبعاد: {self.config.dimensions}")
        except Exception as e:
            logger.error(f"فشل تحميل النموذج: {e}")
            raise

    def _encode_batch(self, texts: List[str]) -> List[List[float]]:
        """ترميز دُفعة من النصوص."""
        if self._model is None:
            raise RuntimeError("النموذج لم يُحمَّل بعد.")
        import numpy as np
        vectors = self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=self.config.show_progress,
        )
        if isinstance(vectors, np.ndarray):
            return vectors.tolist()
        return [v.tolist() for v in vectors]

    @property
    def dimensions(self) -> int:
        if self._loaded and self._model:
            dim = self._model.get_sentence_embedding_dimension()
            return dim if dim else self.config.dimensions
        return self.config.dimensions
