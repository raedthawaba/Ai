"""Phase 8.6 — Citation Injector: حقن المصادر في الاستجابات."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Citation:
    """مصدر واحد."""
    index: int
    title: str = ""
    url: str = ""
    snippet: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet[:200] + "..." if len(self.snippet) > 200 else self.snippet,
            "score": round(self.score, 3),
        }

    def format_inline(self) -> str:
        if self.url:
            return f"[{self.index}] {self.title} — {self.url}"
        return f"[{self.index}] {self.title}"


class CitationInjector:
    """
    حقن المصادر في استجابات الـ AI.

    المهام:
    - استخراج أرقام المصادر من الاستجابة
    - ربطها بالمصادر الفعلية
    - تنسيق قائمة المصادر
    - إضافة روابط
    """

    def __init__(
        self,
        add_citations_section: bool = True,
        language: str = "ar",
        max_citations: int = 10,
    ):
        self.add_citations_section = add_citations_section
        self.language = language
        self.max_citations = max_citations

    def _extract_cited_indices(self, text: str) -> List[int]:
        """استخراج أرقام المصادر المذكورة في النص."""
        pattern = re.compile(r'\[(\d+)\]')
        matches = pattern.findall(text)
        seen = set()
        result = []
        for match in matches:
            idx = int(match)
            if idx not in seen:
                seen.add(idx)
                result.append(idx)
        return result

    def build_citations(
        self,
        sources: List[Dict[str, Any]],
    ) -> List[Citation]:
        """بناء قائمة Citations من sources."""
        citations = []
        for i, source in enumerate(sources[:self.max_citations]):
            citations.append(Citation(
                index=i + 1,
                title=source.get("title", f"مصدر {i + 1}"),
                url=source.get("url", ""),
                snippet=source.get("text", source.get("snippet", "")),
                score=source.get("score", 0.0),
                metadata=source.get("metadata", {}),
            ))
        return citations

    def inject(
        self,
        response_text: str,
        sources: List[Dict[str, Any]],
    ) -> str:
        """حقن المصادر في نص الاستجابة."""
        if not sources or not self.add_citations_section:
            return response_text

        cited_indices = self._extract_cited_indices(response_text)
        citations = self.build_citations(sources)

        if not cited_indices and not citations:
            return response_text

        # تنسيق قسم المصادر
        if self.language == "ar":
            header = "\n\n---\n📚 **المصادر:**\n"
        else:
            header = "\n\n---\n📚 **Sources:**\n"

        # إضافة المصادر المذكورة فقط إذا وُجدت
        relevant_citations = (
            [c for c in citations if c.index in cited_indices]
            if cited_indices
            else citations
        )

        if not relevant_citations:
            relevant_citations = citations

        source_lines = []
        for citation in relevant_citations:
            line = f"**[{citation.index}]** {citation.title}"
            if citation.url:
                line += f" — [{citation.url}]({citation.url})"
            source_lines.append(line)

        return response_text + header + "\n".join(source_lines)

    def format_citations_for_api(
        self,
        sources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """تنسيق المصادر لـ API response."""
        citations = self.build_citations(sources)
        return [c.to_dict() for c in citations]
