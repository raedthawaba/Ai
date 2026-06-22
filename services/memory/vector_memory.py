"""Phase 8.4 — Vector Memory: ذاكرة دلالية مع Vector retrieval."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """إدخال في الذاكرة الدلالية."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    role: str = "user"
    vector: Optional[List[float]] = None
    session_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    importance: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.entry_id,
            "content": self.content,
            "role": self.role,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "importance": self.importance,
        }


class VectorMemory:
    """
    ذاكرة دلالية مع vector retrieval.

    تُخزّن الرسائل كـ vectors وتُسترجع
    بناءً على التشابه الدلالي مع السؤال الحالي.

    مناسبة لـ:
    - استرجاع ذكريات ذات صلة من محادثات سابقة
    - RAG عبر المحادثات
    - Long-term memory
    """

    def __init__(
        self,
        max_entries: int = 1000,
        similarity_threshold: float = 0.7,
        embedding_dim: int = 384,
    ):
        self._entries: List[MemoryEntry] = []
        self.max_entries = max_entries
        self.similarity_threshold = similarity_threshold
        self.embedding_dim = embedding_dim
        self._embedding_model: Optional[Any] = None

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """الحصول على embedding للنص."""
        try:
            if self._embedding_model is None:
                from core.embeddings.embedding_manager import get_embedding_manager
                self._embedding_model = get_embedding_manager()
            result = await self._embedding_model.embed(text)
            return result.vector
        except Exception as e:
            logger.warning("Failed to get embedding: %s", e)
            return None

    def _cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float],
    ) -> float:
        """حساب Cosine Similarity."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    async def store(
        self,
        content: str,
        role: str = "user",
        session_id: Optional[str] = None,
        importance: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """تخزين رسالة في الذاكرة الدلالية."""
        vector = await self._get_embedding(content)

        entry = MemoryEntry(
            content=content,
            role=role,
            vector=vector,
            session_id=session_id,
            importance=importance,
            metadata=metadata or {},
        )

        self._entries.append(entry)

        if len(self._entries) > self.max_entries:
            # حذف الأقل أهمية
            self._entries.sort(key=lambda e: e.importance, reverse=True)
            self._entries = self._entries[:self.max_entries]

        return entry

    async def retrieve_similar(
        self,
        query: str,
        top_k: int = 5,
        session_id: Optional[str] = None,
        min_similarity: Optional[float] = None,
    ) -> List[Tuple[MemoryEntry, float]]:
        """استرجاع الذكريات الأكثر تشابهاً."""
        query_vector = await self._get_embedding(query)
        if not query_vector:
            return self._get_recent(top_k, session_id)

        threshold = min_similarity or self.similarity_threshold
        scored: List[Tuple[MemoryEntry, float]] = []

        entries = (
            [e for e in self._entries if e.session_id == session_id]
            if session_id else self._entries
        )

        for entry in entries:
            if entry.vector:
                sim = self._cosine_similarity(query_vector, entry.vector)
                if sim >= threshold:
                    scored.append((entry, sim))

        scored.sort(key=lambda x: x[1] * x[0].importance, reverse=True)
        return scored[:top_k]

    def _get_recent(
        self,
        n: int,
        session_id: Optional[str] = None,
    ) -> List[Tuple[MemoryEntry, float]]:
        """استرجاع أحدث الذكريات كـ fallback."""
        entries = (
            [e for e in self._entries if e.session_id == session_id]
            if session_id else self._entries
        )
        return [(e, 1.0) for e in sorted(entries, key=lambda e: e.timestamp, reverse=True)[:n]]

    def clear_session(self, session_id: str) -> int:
        """حذف ذكريات جلسة معينة."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.session_id != session_id]
        return before - len(self._entries)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "max_entries": self.max_entries,
            "with_vectors": sum(1 for e in self._entries if e.vector),
            "sessions": len({e.session_id for e in self._entries if e.session_id}),
        }
