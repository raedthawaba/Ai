"""Context Assembler — تجميع السياق للـ RAG مع token budget."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_WORDS_PER_TOKEN = 0.75  # تقريب عام


@dataclass
class ContextChunk:
    chunk_id: str
    article_id: str
    text: str
    score: float
    source_url: str = ""
    source_title: str = ""
    rank: int = 0
    token_estimate: int = 0

    def __post_init__(self) -> None:
        self.token_estimate = max(1, int(len(self.text.split()) / _WORDS_PER_TOKEN))


@dataclass
class AssembledContext:
    chunks: List[ContextChunk]
    full_text: str
    total_tokens: int
    sources: List[Dict]
    query: str
    budget_used_pct: float
    truncated: bool = False

    def to_prompt_block(self, header: str = "CONTEXT") -> str:
        lines = [f"[{header}]"]
        for i, ch in enumerate(self.chunks, 1):
            title = ch.source_title or ch.source_url or f"مصدر {i}"
            lines.append(f"\n--- [{i}] {title} ---")
            lines.append(ch.text.strip() if ch.text.strip() else ch.text)
        return "\n".join(lines)


class ContextAssembler:
    """
    يُجمّع chunks في سياق نهائي مع:
    - token budget management
    - deduplication
    - chunk prioritization بالسكور
    - citation-ready sources
    - العربية + الإنجليزية
    """

    def __init__(
        self,
        max_tokens: int = 4096,
        reserve_tokens: int = 512,
        min_chunk_tokens: int = 1,
        deduplicate_threshold: float = 0.85,
    ) -> None:
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.min_chunk_tokens = min_chunk_tokens
        self.deduplicate_threshold = deduplicate_threshold
        self._context_budget = max_tokens - reserve_tokens

    def assemble(
        self,
        hits: List[Any],
        query: str,
        max_chunks: Optional[int] = None,
    ) -> AssembledContext:
        """
        hits: list من RetrievalHit أو dict مع {chunk_id, article_id, text, score}
        """
        # تحويل إلى ContextChunk
        chunks = self._to_context_chunks(hits)

        # فرز بالسكور
        chunks.sort(key=lambda c: c.score, reverse=True)

        # إزالة التكرار
        chunks = self._deduplicate(chunks)

        # تطبيق token budget
        selected, total_tokens, truncated = self._apply_budget(chunks, max_chunks)

        # بناء النص الكامل
        full_text = self._build_text(selected)

        # مصادر فريدة
        sources = self._build_sources(selected)

        budget_pct = round(total_tokens / self._context_budget * 100, 1) if self._context_budget > 0 else 0

        logger.info(
            "ContextAssembler: chunks=%d tokens=%d/~%d (%.1f%%) truncated=%s",
            len(selected), total_tokens, self._context_budget, budget_pct, truncated,
        )

        return AssembledContext(
            chunks=selected,
            full_text=full_text,
            total_tokens=total_tokens,
            sources=sources,
            query=query,
            budget_used_pct=budget_pct,
            truncated=truncated,
        )

    # ─── Internal ────────────────────────────────────────────────────────────

    def _to_context_chunks(self, hits: List[Any]) -> List[ContextChunk]:
        chunks = []
        for i, h in enumerate(hits):
            if isinstance(h, dict):
                text = h.get("text", "")
                ch = ContextChunk(
                    chunk_id=h.get("chunk_id", f"chunk_{i}"),
                    article_id=h.get("article_id", ""),
                    text=text,
                    score=float(h.get("score", 0.0)),
                    source_url=h.get("source_url", h.get("metadata", {}).get("source_url", "")),
                    source_title=h.get("source_title", h.get("metadata", {}).get("source_title", "")),
                    rank=i + 1,
                )
            else:
                # RetrievalHit object
                ch = ContextChunk(
                    chunk_id=getattr(h, "chunk_id", f"chunk_{i}"),
                    article_id=getattr(h, "article_id", ""),
                    text=getattr(h, "text", ""),
                    score=float(getattr(h, "score", 0.0)),
                    source_url=getattr(h, "source_url", ""),
                    source_title=getattr(h, "source_title", ""),
                    rank=i + 1,
                )
            if ch.token_estimate >= self.min_chunk_tokens:
                chunks.append(ch)
        return chunks

    def _deduplicate(self, chunks: List[ContextChunk]) -> List[ContextChunk]:
        unique: List[ContextChunk] = []
        for ch in chunks:
            if not self._is_duplicate(ch, unique):
                unique.append(ch)
        return unique

    def _is_duplicate(self, chunk: ContextChunk, existing: List[ContextChunk]) -> bool:
        tokens_a = set(chunk.text.lower().split())
        for ex in existing:
            tokens_b = set(ex.text.lower().split())
            union = tokens_a | tokens_b
            if not union:
                continue
            jaccard = len(tokens_a & tokens_b) / len(union)
            if jaccard >= self.deduplicate_threshold:
                return True
        return False

    def _apply_budget(
        self,
        chunks: List[ContextChunk],
        max_chunks: Optional[int],
    ) -> tuple:
        selected = []
        used_tokens = 0
        truncated = False

        for ch in chunks:
            if max_chunks and len(selected) >= max_chunks:
                truncated = True
                break
            if used_tokens + ch.token_estimate > self._context_budget:
                truncated = True
                break
            selected.append(ch)
            used_tokens += ch.token_estimate

        return selected, used_tokens, truncated

    def _build_text(self, chunks: List[ContextChunk]) -> str:
        parts = []
        for i, ch in enumerate(chunks, 1):
            parts.append(f"[{i}] {ch.text.strip()}")
        return "\n\n".join(parts)

    def _build_sources(self, chunks: List[ContextChunk]) -> List[Dict]:
        seen: set = set()
        sources = []
        for i, ch in enumerate(chunks, 1):
            key = ch.article_id or ch.source_url
            if key and key not in seen:
                seen.add(key)
                sources.append({
                    "citation_index": i,
                    "article_id": ch.article_id,
                    "source_url": ch.source_url,
                    "source_title": ch.source_title or f"مصدر {i}",
                    "relevance_score": round(ch.score, 4),
                })
        return sources
