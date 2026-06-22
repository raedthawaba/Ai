from __future__ import annotations

import logging
import math
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class EmbeddingModelLoader:
    """Load and run sentence-transformer (or HuggingFace) embedding models."""

    def load(self, model_name: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            model = SentenceTransformer(model_name)
            logger.info("SentenceTransformer loaded: %s", model_name)
            return model
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Using HuggingFace AutoModel fallback."
            )
            return self._load_hf(model_name)

    def _load_hf(self, model_name: str) -> Any:
        try:
            from transformers import AutoTokenizer, AutoModel  # type: ignore
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name)
            return {"tokenizer": tokenizer, "model": model, "type": "hf"}
        except Exception as exc:
            logger.error("Cannot load embedding model '%s': %s", model_name, exc)
            raise

    def encode(
        self,
        model: Any,
        texts: List[str],
        normalize: bool = True,
    ) -> List[List[float]]:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            if isinstance(model, SentenceTransformer):
                vecs = model.encode(texts, normalize_embeddings=normalize, show_progress_bar=False)
                return [v.tolist() for v in vecs]
        except ImportError:
            pass

        if isinstance(model, dict) and model.get("type") == "hf":
            return self._hf_encode(model, texts, normalize)

        raise TypeError(f"Unsupported model type: {type(model)}")

    def _hf_encode(self, model_dict: dict, texts: List[str], normalize: bool) -> List[List[float]]:
        import torch  # type: ignore

        tokenizer = model_dict["tokenizer"]
        model = model_dict["model"]
        encoded = tokenizer(texts, padding=True, truncation=True, return_tensors="pt", max_length=512)
        with torch.no_grad():
            output = model(**encoded)
        vecs = output.last_hidden_state[:, 0, :].tolist()
        if normalize:
            vecs = [self._normalize(v) for v in vecs]
        return vecs

    @staticmethod
    def _normalize(vec: List[float]) -> List[float]:
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]

    def get_dimensions(self, model: Any) -> int:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            if isinstance(model, SentenceTransformer):
                return model.get_sentence_embedding_dimension()
        except ImportError:
            pass
        if isinstance(model, dict) and model.get("type") == "hf":
            hf_model = model["model"]
            return hf_model.config.hidden_size
        return 384
