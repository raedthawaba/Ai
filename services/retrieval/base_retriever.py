"""Base Retriever abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RetrievalResult:
    """الـ context المُسترجع من قاعدة البيانات الدلالية."""
    query: str
    chunks: List[Dict] = field(default_factory=list)
    total_retrieved: int = 0
    retrieval_time_ms: float = 0.0
    retriever_name: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_context_text(self, separator: str = "\n\n---\n\n") -> str:
        """تحويل الـ chunks إلى نص context متسلسل."""
        parts = []
        for i, chunk in enumerate(self.chunks, 1):
            text = chunk.get("text", "")
            source = chunk.get("source_url", "") or chunk.get("article_id", "")
            parts.append(f"[{i}] {text}\n(المصدر: {source})")
        return separator.join(parts)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "total_retrieved": self.total_retrieved,
            "retrieval_time_ms": round(self.retrieval_time_ms, 3),
            "retriever_name": self.retriever_name,
            "chunks": self.chunks,
        }


class BaseRetriever(ABC):
    """الواجهة المجردة لجميع Retrievers."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict] = None,
    ) -> RetrievalResult:
        """استرجاع الـ chunks الأكثر صلة بالاستعلام."""
        ...

    async def retrieve_and_format(self, query: str, top_k: int = 5) -> str:
        """استرجاع وتحويل مباشر إلى نص."""
        result = await self.retrieve(query, top_k=top_k)
        return result.to_context_text()
