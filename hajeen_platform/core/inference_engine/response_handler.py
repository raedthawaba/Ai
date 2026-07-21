"""Phase 8.3 — Response Handler: معالجة وتنظيف استجابات الـ LLM."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .llm.base import LLMResponse


@dataclass
class ProcessedResponse:
    """استجابة معالجة ونظيفة."""
    raw_content: str
    cleaned_content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    finish_reason: str
    request_id: Optional[str]
    processing_ms: float = 0.0
    citations: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content": self.cleaned_content,
            "model": self.model,
            "provider": self.provider,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "latency_ms": round(self.latency_ms, 2),
            "finish_reason": self.finish_reason,
            "citations": self.citations,
        }


class ResponseHandler:
    """
    معالجة استجابات LLM.

    المهام:
    - تنظيف النصوص
    - استخراج الاقتباسات
    - تنسيق الإخراج
    - إحصاء التوكنات
    """

    # أنماط للتنظيف
    CLEANUP_PATTERNS = [
        (r'\n{3,}', '\n\n'),
        (r'[ \t]+\n', '\n'),
        (r'^\s+', ''),
    ]

    def __init__(
        self,
        strip_thinking_tags: bool = True,
        normalize_whitespace: bool = True,
        extract_citations: bool = True,
    ):
        self.strip_thinking = strip_thinking_tags
        self.normalize_ws = normalize_whitespace
        self.extract_citations_flag = extract_citations

    def _clean_text(self, text: str) -> str:
        """تنظيف نص الاستجابة."""
        if self.strip_thinking:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)

        if self.normalize_ws:
            for pattern, replacement in self.CLEANUP_PATTERNS:
                text = re.sub(pattern, replacement, text, flags=re.MULTILINE)

        return text.strip()

    def _extract_citations(self, text: str) -> List[Dict[str, Any]]:
        """استخراج أرقام المصادر من النص."""
        citation_pattern = re.compile(r'\[(\d+)\]')
        found_indices = set()
        matches = citation_pattern.findall(text)
        for match in matches:
            found_indices.add(int(match))
        return [{"index": i} for i in sorted(found_indices)]

    def process(
        self,
        response: LLMResponse,
        processing_start: Optional[float] = None,
    ) -> ProcessedResponse:
        """معالجة LLMResponse وإرجاع ProcessedResponse."""
        t0 = processing_start or time.perf_counter()

        cleaned = self._clean_text(response.content)

        citations = []
        if self.extract_citations_flag:
            citations = self._extract_citations(cleaned)

        processing_ms = (time.perf_counter() - t0) * 1000

        return ProcessedResponse(
            raw_content=response.content,
            cleaned_content=cleaned,
            model=response.model,
            provider=response.provider,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            latency_ms=response.latency_ms,
            finish_reason=response.finish_reason,
            request_id=response.request_id,
            processing_ms=processing_ms,
            citations=citations,
            metadata=response.metadata,
        )

    def process_batch(self, responses: List[LLMResponse]) -> List[ProcessedResponse]:
        """معالجة دفعة من الاستجابات."""
        return [self.process(r) for r in responses]

    def format_for_api(self, processed: ProcessedResponse) -> dict:
        """تنسيق للـ API response."""
        return {
            "response": processed.cleaned_content,
            "model": processed.model,
            "provider": processed.provider,
            "usage": {
                "prompt_tokens": processed.prompt_tokens,
                "completion_tokens": processed.completion_tokens,
                "total_tokens": processed.total_tokens,
            },
            "latency_ms": round(processed.latency_ms, 2),
            "citations": processed.citations,
        }
