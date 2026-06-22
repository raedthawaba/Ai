"""Context Assembler — يبني context جاهز للـ LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.retrieval.base_retriever import RetrievalResult


@dataclass
class AssembledContext:
    """الـ context المُجمَّع والجاهز للـ LLM."""
    query: str
    context_text: str
    chunks: List[Dict] = field(default_factory=list)
    total_tokens_estimate: int = 0
    sources: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "context_text": self.context_text[:2000],
            "total_tokens_estimate": self.total_tokens_estimate,
            "sources": self.sources,
            "num_chunks": len(self.chunks),
        }


class ContextAssembler:
    """
    يحوّل نتائج الـ Retriever إلى context منسّق جاهز للـ LLM.

    Query → Retriever → [chunks] → ContextAssembler → AssembledContext
    """

    def __init__(
        self,
        max_context_chars: int = 4000,
        chunk_separator: str = "\n\n---\n\n",
        include_sources: bool = True,
        deduplicate: bool = True,
    ):
        self.max_context_chars = max_context_chars
        self.chunk_separator = chunk_separator
        self.include_sources = include_sources
        self.deduplicate = deduplicate

    def assemble(self, retrieval_result: RetrievalResult) -> AssembledContext:
        """بناء context من نتائج الـ Retriever."""
        chunks = retrieval_result.chunks

        if self.deduplicate:
            chunks = self._deduplicate(chunks)

        # ترتيب بالـ score
        chunks = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)

        parts = []
        sources = []
        total_chars = 0

        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "").strip()
            if not text:
                continue

            source_url = chunk.get("source_url", "")
            source_title = chunk.get("source_title", "") or chunk.get("article_id", "")
            score = chunk.get("score", 0)

            if self.include_sources:
                header = f"[{i}] (score: {score:.3f})"
                if source_title:
                    header += f" — {source_title}"
                chunk_text = f"{header}\n{text}"
            else:
                chunk_text = text

            if total_chars + len(chunk_text) > self.max_context_chars:
                break

            parts.append(chunk_text)
            total_chars += len(chunk_text)

            if source_url and source_url not in sources:
                sources.append(source_url)

        context_text = self.chunk_separator.join(parts)
        token_estimate = len(context_text.split()) * 1  # تقدير تقريبي: 1 token ≈ 1 كلمة

        return AssembledContext(
            query=retrieval_result.query,
            context_text=context_text,
            chunks=chunks[: len(parts)],
            total_tokens_estimate=token_estimate,
            sources=sources,
            metadata={
                "retriever": retrieval_result.retriever_name,
                "retrieval_time_ms": retrieval_result.retrieval_time_ms,
                "num_sources": len(sources),
            },
        )

    def _deduplicate(self, chunks: List[Dict]) -> List[Dict]:
        """إزالة الـ chunks المتشابهة جداً."""
        seen_texts = []
        unique = []
        for chunk in chunks:
            text = chunk.get("text", "")[:100]
            if text not in seen_texts:
                seen_texts.append(text)
                unique.append(chunk)
        return unique
