"""Embedding Generator Interface — Phase 6.5.

واجهة مجردة لمولّدات الـ embeddings.
يمكن تنفيذها لـ:
  - OpenAI (text-embedding-3-small/large)
  - Anthropic
  - HuggingFace Transformers
  - Sentence Transformers (محلياً)
  - Google Gemini Embeddings
  - Mock (للاختبار)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.utils.datetime_utils import utc_now


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmbeddingConfig:
    """إعدادات مولّد الـ embeddings."""

    model_name: str = "text-embedding-3-small"
    dimensions: int = 1536           # OpenAI text-embedding-3-small
    batch_size: int = 32             # حجم دُفعة الطلبات
    max_tokens: int = 8192           # حد الـ tokens لكل نص
    normalize: bool = True           # تطبيع إلى وحدة طول (L2)
    provider: str = "mock"           # "openai" | "huggingface" | "mock"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingRequest:
    """طلب حساب embedding لنص واحد."""

    request_id: str
    text: str
    source_id: str           # معرّف المصدر (article_id أو chunk_id)
    source_type: str = "chunk"    # "article" | "chunk"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResult:
    """نتيجة embedding لنص واحد."""

    request_id: str
    source_id: str
    source_type: str
    vector: List[float]
    dimensions: int
    model_name: str
    provider: str
    token_count: int = 0
    processing_ms: float = 0.0
    created_at: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return not self.error and len(self.vector) == self.dimensions

    @property
    def embedding_id(self) -> str:
        """معرّف فريد للـ embedding."""
        import hashlib
        key = f"{self.source_id}::{self.model_name}::{self.dimensions}"
        return "emb_" + hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "embedding_id": self.embedding_id,
            "dimensions": self.dimensions,
            "model_name": self.model_name,
            "provider": self.provider,
            "token_count": self.token_count,
            "processing_ms": self.processing_ms,
            "created_at": self.created_at.isoformat(),
            "error": self.error,
            "vector_preview": self.vector[:5] if self.vector else [],
        }


# ─────────────────────────────────────────────────────────────────────────────
# BaseEmbedder
# ─────────────────────────────────────────────────────────────────────────────

class BaseEmbedder(ABC):
    """واجهة مجردة لمولّدات الـ embeddings.

    كل مزوّد (OpenAI, HuggingFace, etc.) يُنفّذ هذه الواجهة.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None) -> None:
        self.config = config or EmbeddingConfig()

    @property
    @abstractmethod
    def provider(self) -> str:
        """اسم المزوّد."""

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def dimensions(self) -> int:
        return self.config.dimensions

    @abstractmethod
    async def embed_one(self, request: EmbeddingRequest) -> EmbeddingResult:
        """حساب embedding لنص واحد."""

    @abstractmethod
    async def embed_batch(
        self, requests: List[EmbeddingRequest]
    ) -> List[EmbeddingResult]:
        """حساب embeddings لدُفعة من النصوص."""

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """فحص صحة الاتصال بمزوّد الـ embeddings."""

    async def embed_text(
        self,
        text: str,
        source_id: str = "unknown",
        source_type: str = "chunk",
    ) -> EmbeddingResult:
        """Helper — تضمين نص مع إنشاء EmbeddingRequest تلقائي."""
        import uuid
        request = EmbeddingRequest(
            request_id=str(uuid.uuid4())[:8],
            text=text,
            source_id=source_id,
            source_type=source_type,
        )
        return await self.embed_one(request)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"provider={self.provider!r} "
            f"model={self.model_name!r} "
            f"dims={self.dimensions})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# MockEmbedder — للاختبار والتطوير
# ─────────────────────────────────────────────────────────────────────────────

class MockEmbedder(BaseEmbedder):
    """مولّد embeddings وهمي للاختبار.

    يُنتج vectors عشوائية ثابتة بناءً على محتوى النص.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None) -> None:
        super().__init__(config or EmbeddingConfig(
            model_name="mock-embedding-v1",
            dimensions=384,
            provider="mock",
        ))

    @property
    def provider(self) -> str:
        return "mock"

    async def embed_one(self, request: EmbeddingRequest) -> EmbeddingResult:
        import time
        import hashlib
        import math

        t0 = time.time()

        # توليد vector ثابت بناءً على هاش النص
        text_hash = hashlib.sha256(request.text.encode()).digest()
        dims = self.config.dimensions
        vector: List[float] = []
        for i in range(dims):
            byte_val = text_hash[i % len(text_hash)]
            # تحويل إلى قيمة في [-1, 1]
            val = (byte_val / 127.5) - 1.0
            vector.append(round(val, 6))

        # تطبيع L2
        if self.config.normalize:
            magnitude = math.sqrt(sum(v * v for v in vector))
            if magnitude > 0:
                vector = [round(v / magnitude, 6) for v in vector]

        ms = (time.time() - t0) * 1000
        token_count = max(1, len(request.text) // 4)

        return EmbeddingResult(
            request_id=request.request_id,
            source_id=request.source_id,
            source_type=request.source_type,
            vector=vector,
            dimensions=dims,
            model_name=self.config.model_name,
            provider="mock",
            token_count=token_count,
            processing_ms=ms,
            metadata=request.metadata,
        )

    async def embed_batch(
        self, requests: List[EmbeddingRequest]
    ) -> List[EmbeddingResult]:
        results = []
        for req in requests:
            results.append(await self.embed_one(req))
        return results

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "provider": "mock", "model": self.config.model_name}


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

_EMBEDDER_REGISTRY: Dict[str, type] = {
    "mock": MockEmbedder,
}


def register_embedder(provider: str, embedder_class: type) -> None:
    """تسجيل مزوّد embeddings جديد."""
    _EMBEDDER_REGISTRY[provider.lower()] = embedder_class


def create_embedder(
    provider: str = "mock",
    config: Optional[EmbeddingConfig] = None,
) -> BaseEmbedder:
    """إنشاء embedder بناءً على المزوّد.

    Parameters
    ----------
    provider:
        "mock" | "openai" | "huggingface" | ...
    config:
        EmbeddingConfig اختياري.
    """
    cls = _EMBEDDER_REGISTRY.get(provider.lower())
    if cls is None:
        raise ValueError(
            f"مزوّد embeddings غير مدعوم: {provider!r}. "
            f"المتاح: {list(_EMBEDDER_REGISTRY.keys())}"
        )
    return cls(config)
