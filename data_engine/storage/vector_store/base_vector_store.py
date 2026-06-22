"""Base abstractions for vector storage."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class VectorEntry:
    """سجل embedding واحد في Vector Store."""
    id: str
    vector: List[float]
    chunk_id: str
    article_id: str
    text: str = ""
    model_name: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """نتيجة بحث واحدة من Vector Store."""
    chunk_id: str
    article_id: str
    score: float
    text: str = ""
    model_name: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "score": round(self.score, 6),
            "text": self.text[:200] if self.text else "",
            "model_name": self.model_name,
            "metadata": self.metadata,
        }


@dataclass
class VectorStoreStats:
    total_vectors: int = 0
    index_type: str = ""
    dimensions: int = 0
    is_trained: bool = False
    extra: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_vectors": self.total_vectors,
            "index_type": self.index_type,
            "dimensions": self.dimensions,
            "is_trained": self.is_trained,
            **self.extra,
        }


class BaseVectorStore(ABC):
    """واجهة مجردة لجميع Vector Stores."""

    @abstractmethod
    def add(self, entries: List[VectorEntry]) -> int:
        """إضافة vectors — يُعيد عدد المُضافة."""
        ...

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """بحث بالتشابه — يُعيد أفضل top_k نتيجة."""
        ...

    @abstractmethod
    def delete(self, ids: List[str]) -> int:
        """حذف vectors بالمعرّف."""
        ...

    @abstractmethod
    def stats(self) -> VectorStoreStats:
        """إحصائيات الـ index الحالي."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """حفظ الـ index على القرص."""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """تحميل الـ index من القرص."""
        ...

    def batch_add(self, entries: List[VectorEntry], batch_size: int = 1000) -> int:
        """إضافة batch بدُفعات."""
        total = 0
        for i in range(0, len(entries), batch_size):
            total += self.add(entries[i : i + batch_size])
        return total
