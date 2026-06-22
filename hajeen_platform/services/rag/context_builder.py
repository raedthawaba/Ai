"""Context Builder — يبني context من chunks متعددة."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.retrieval.context_assembler import AssembledContext


@dataclass
class BuiltContext:
    """Context مبني وجاهز للـ prompt."""
    raw_chunks: List[Dict]
    formatted_text: str
    sources: List[str]
    total_chars: int
    total_tokens_estimate: int
    metadata: Dict = field(default_factory=dict)


class ContextBuilder:
    """
    يحوّل AssembledContext إلى context منسّق للـ prompt.
    يدعم:
    - تحديد الحد الأقصى للـ tokens
    - تنسيق مع أو بدون أرقام المصادر
    - window truncation
    """

    def __init__(
        self,
        max_tokens: int = 2000,
        context_style: str = "numbered",
    ):
        self.max_tokens = max_tokens
        self.context_style = context_style

    def build(self, assembled: AssembledContext) -> BuiltContext:
        chunks = assembled.chunks
        lines = []
        used_tokens = 0

        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "").strip()
            if not text:
                continue
            token_est = len(text.split())
            if used_tokens + token_est > self.max_tokens:
                break
            if self.context_style == "numbered":
                lines.append(f"[{i}] {text}")
            else:
                lines.append(text)
            used_tokens += token_est

        formatted = "\n\n".join(lines)
        return BuiltContext(
            raw_chunks=chunks[: len(lines)],
            formatted_text=formatted,
            sources=assembled.sources,
            total_chars=len(formatted),
            total_tokens_estimate=used_tokens,
            metadata=assembled.metadata,
        )
