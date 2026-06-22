"""Citation Manager — يدير المصادر والاستشهادات."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Citation:
    """استشهاد واحد بمصدر."""
    index: int
    chunk_id: str
    article_id: str
    source_url: str = ""
    source_title: str = ""
    text_preview: str = ""
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "text_preview": self.text_preview[:150],
            "score": round(self.score, 4),
        }


class CitationManager:
    """يُدير قائمة المصادر المرجعية لاستجابة الـ RAG."""

    def __init__(self):
        self._citations: List[Citation] = []

    def add_from_chunks(self, chunks: List[Dict]) -> None:
        for i, chunk in enumerate(chunks, 1):
            citation = Citation(
                index=i,
                chunk_id=chunk.get("chunk_id", ""),
                article_id=chunk.get("article_id", ""),
                source_url=chunk.get("source_url", ""),
                source_title=chunk.get("source_title", ""),
                text_preview=chunk.get("text", "")[:150],
                score=chunk.get("score", 0.0),
            )
            self._citations.append(citation)

    def get_all(self) -> List[Citation]:
        return list(self._citations)

    def format_references(self) -> str:
        if not self._citations:
            return ""
        lines = ["المصادر:"]
        for c in self._citations:
            title = c.source_title or c.article_id
            url = f" ({c.source_url})" if c.source_url else ""
            lines.append(f"[{c.index}] {title}{url}")
        return "\n".join(lines)

    def to_dict_list(self) -> List[Dict]:
        return [c.to_dict() for c in self._citations]
