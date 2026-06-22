"""Phase 8.2 — Context Injector: حقن سياق RAG في الـ prompts."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InjectedContext:
    """سياق محقون في prompt."""
    text: str
    source_count: int
    token_estimate: int
    truncated: bool = False
    sources: List[Dict[str, Any]] = field(default_factory=list)


class ContextInjector:
    """
    حقن سياق RAG في الـ prompts.

    المهام:
    - دمج نصوص المصادر
    - ترتيبها حسب الأولوية
    - قصها عند الحاجة
    - إضافة أرقام المصادر
    """

    def __init__(
        self,
        max_context_tokens: int = 2000,
        tokens_per_word: float = 1.3,
        include_source_numbers: bool = True,
        separator: str = "\n---\n",
    ):
        self.max_context_tokens = max_context_tokens
        self.tokens_per_word = tokens_per_word
        self.include_source_numbers = include_source_numbers
        self.separator = separator

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * self.tokens_per_word)

    def inject(
        self,
        chunks: List[Dict[str, Any]],
        query: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> InjectedContext:
        """
        حقن chunks في context.

        كل chunk يجب أن يحتوي على: text, (اختياري) title, url, score
        """
        limit = max_tokens or self.max_context_tokens
        parts: List[str] = []
        used_tokens = 0
        truncated = False
        sources = []

        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            title = chunk.get("title", "")
            url = chunk.get("url", "")
            score = chunk.get("score", 0.0)

            if not text:
                continue

            chunk_tokens = self._estimate_tokens(text)

            if used_tokens + chunk_tokens > limit:
                remaining = limit - used_tokens
                if remaining < 50:
                    truncated = True
                    break
                words = text.split()
                allowed_words = int(remaining / self.tokens_per_word)
                text = " ".join(words[:allowed_words]) + "..."
                chunk_tokens = self._estimate_tokens(text)
                truncated = True

            if self.include_source_numbers:
                header = f"[{i + 1}]"
                if title:
                    header += f" {title}"
                parts.append(f"{header}\n{text}")
            else:
                parts.append(text)

            sources.append({
                "index": i + 1,
                "title": title,
                "url": url,
                "score": score,
            })

            used_tokens += chunk_tokens

            if truncated:
                break

        combined = self.separator.join(parts)

        return InjectedContext(
            text=combined,
            source_count=len(sources),
            token_estimate=used_tokens,
            truncated=truncated,
            sources=sources,
        )

    def inject_from_rag_result(
        self,
        rag_result: Any,
        max_tokens: Optional[int] = None,
    ) -> InjectedContext:
        """حقن من نتيجة RAGPipeline مباشرة."""
        chunks = []
        try:
            for chunk in getattr(rag_result, "chunks", []):
                chunks.append({
                    "text": getattr(chunk, "text", ""),
                    "title": getattr(chunk, "title", ""),
                    "url": getattr(chunk, "url", ""),
                    "score": getattr(chunk, "score", 0.0),
                })
        except Exception as e:
            logger.warning("Failed to extract chunks from RAG result: %s", e)

        return self.inject(chunks, max_tokens=max_tokens)
