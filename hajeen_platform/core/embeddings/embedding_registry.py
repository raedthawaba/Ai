"""سجل نماذج الـ embedding — يدعم تسجيل نماذج مخصصة."""
from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from core.embeddings.base import BaseEmbeddingModel, EmbeddingConfig

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[BaseEmbeddingModel]] = {}


def register_embedding_model(name: str, cls: Type[BaseEmbeddingModel]) -> None:
    """تسجيل نموذج embedding جديد."""
    _REGISTRY[name] = cls
    logger.debug(f"تسجيل نموذج: {name}")


def get_registered_models() -> Dict[str, Type[BaseEmbeddingModel]]:
    return dict(_REGISTRY)


def create_embedding_model(
    name: str,
    config: Optional[EmbeddingConfig] = None,
) -> BaseEmbeddingModel:
    """إنشاء نموذج embedding بالاسم."""
    if name not in _REGISTRY:
        available = list(_REGISTRY.keys())
        raise ValueError(f"نموذج '{name}' غير مسجّل. المتاح: {available}")
    cls = _REGISTRY[name]
    return cls(config)


class EmbeddingRegistry:
    """واجهة موحّدة لسجل النماذج."""

    @staticmethod
    def register(name: str, cls: Type[BaseEmbeddingModel]) -> None:
        register_embedding_model(name, cls)

    @staticmethod
    def create(name: str, config: Optional[EmbeddingConfig] = None) -> BaseEmbeddingModel:
        return create_embedding_model(name, config)

    @staticmethod
    def list_models() -> list[str]:
        return list(_REGISTRY.keys())


# ─── تسجيل النماذج الافتراضية ───────────────────────────────────────────────
def _register_defaults() -> None:
    try:
        from core.embeddings.sentence_transformer import SentenceTransformerModel
        register_embedding_model("sentence-transformers", SentenceTransformerModel)
        register_embedding_model("all-MiniLM-L6-v2", SentenceTransformerModel)
    except ImportError:
        logger.warning("sentence-transformers غير متاح — يُستخدم النموذج الوهمي فقط.")


_register_defaults()
