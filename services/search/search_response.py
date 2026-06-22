"""نماذج بيانات استجابة البحث."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SearchHit:
    """نتيجة بحث واحدة."""
    chunk_id: str
    article_id: str
    text: str
    score: float
    rank: int
    model_name: str = ""
    metadata: Dict = field(default_factory=dict)
    source_url: str = ""
    source_title: str = ""

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "text": self.text[:300] if self.text else "",
            "score": round(self.score, 6),
            "source_url": self.source_url,
            "source_title": self.source_title,
            "metadata": self.metadata,
        }


@dataclass
class SearchResponse:
    """الاستجابة الكاملة لطلب البحث."""
    query: str
    hits: List[SearchHit] = field(default_factory=list)
    total_found: int = 0
    search_time_ms: float = 0.0
    model_name: str = ""
    query_vector_preview: List[float] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    search_type: str = "semantic"
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "search_type": self.search_type,
            "total_found": self.total_found,
            "search_time_ms": round(self.search_time_ms, 3),
            "model_name": self.model_name,
            "hits": [h.to_dict() for h in self.hits],
            "metadata": self.metadata,
        }
