"""Response Formatter — يُنسّق استجابة الـ RAG."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FormattedResponse:
    """الاستجابة النهائية المُنسّقة."""
    query: str
    answer_placeholder: str
    context_used: str
    citations: List[Dict]
    prompt_ready: str
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "status": "ready_for_llm",
            "answer_placeholder": self.answer_placeholder,
            "context_chars": len(self.context_used),
            "num_citations": len(self.citations),
            "citations": self.citations,
            "metadata": self.metadata,
        }


class ResponseFormatter:
    """يُنسّق الاستجابة النهائية من RAG pipeline."""

    def format(
        self,
        query: str,
        context_text: str,
        prompt: str,
        citations: List[Dict],
        retrieval_ms: float = 0.0,
    ) -> FormattedResponse:
        return FormattedResponse(
            query=query,
            answer_placeholder="[جاهز للـ LLM — Phase 8]",
            context_used=context_text,
            citations=citations,
            prompt_ready=prompt,
            metadata={
                "retrieval_time_ms": round(retrieval_ms, 2),
                "context_length": len(context_text),
                "num_sources": len({c.get("article_id") for c in citations}),
                "prompt_length": len(prompt),
            },
        )
