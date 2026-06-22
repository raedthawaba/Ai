from __future__ import annotations

import re
from typing import Dict, List, Optional

from .retriever import RetrievalResult


class CitationBuilder:
    """Build inline citations and reference lists from retrieved documents."""

    def __init__(self, style: str = "numbered") -> None:
        self.style = style

    def inject_citations(self, text: str, results: List[RetrievalResult]) -> str:
        """Map [1], [2] placeholders in text to source references."""
        ref_map: Dict[int, str] = {}
        for i, result in enumerate(results):
            source = result.metadata.get("source", result.metadata.get("url", result.doc_id))
            ref_map[i + 1] = source

        def replacer(m: re.Match) -> str:
            num = int(m.group(1))
            src = ref_map.get(num, "")
            return f"[{num}]({src})" if src else f"[{num}]"

        return re.sub(r"\[(\d+)\]", replacer, text)

    def build_references(self, results: List[RetrievalResult]) -> str:
        if not results:
            return ""
        lines = ["\n**References:**"]
        for i, result in enumerate(results):
            source = result.metadata.get("source", result.metadata.get("url", result.doc_id))
            title = result.metadata.get("title", source)
            score_str = f" (score: {result.score:.3f})" if result.score else ""
            lines.append(f"{i + 1}. {title}{score_str}")
        return "\n".join(lines)

    def build_source_list(self, results: List[RetrievalResult]) -> List[Dict]:
        return [
            {
                "index": i + 1,
                "doc_id": r.doc_id,
                "source": r.metadata.get("source", r.metadata.get("url", r.doc_id)),
                "title": r.metadata.get("title", r.doc_id),
                "score": round(r.score, 4),
                "snippet": r.content[:200] + ("..." if len(r.content) > 200 else ""),
            }
            for i, r in enumerate(results)
        ]
