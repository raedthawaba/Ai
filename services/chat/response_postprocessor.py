"""Phase 8.6 — Response Postprocessor: معالجة استجابات الـ AI."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PostprocessedResponse:
    """استجابة معالجة ونهائية."""
    content: str
    original_content: str
    language: str = "ar"
    word_count: int = 0
    has_code: bool = False
    has_lists: bool = False
    citations_injected: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "language": self.language,
            "word_count": self.word_count,
            "has_code": self.has_code,
            "has_lists": self.has_lists,
        }


class ResponsePostprocessor:
    """
    معالجة ما بعد الاستجابة.

    المهام:
    - تنظيف النصوص
    - كشف اللغة
    - تنسيق Markdown
    - إزالة التكرار
    - إحصاء الكلمات
    - كشف الكود والقوائم
    """

    def __init__(
        self,
        fix_arabic_punctuation: bool = True,
        normalize_whitespace: bool = True,
        remove_repetition: bool = True,
    ):
        self.fix_arabic_punctuation = fix_arabic_punctuation
        self.normalize_ws = normalize_whitespace
        self.remove_repetition = remove_repetition

    def _detect_language(self, text: str) -> str:
        arabic = len(re.findall(r'[\u0600-\u06FF]', text))
        latin = len(re.findall(r'[a-zA-Z]', text))
        if arabic > latin:
            return "ar"
        elif latin > 0:
            return "en"
        return "unknown"

    def _fix_arabic(self, text: str) -> str:
        """إصلاح علامات الترقيم العربية."""
        text = re.sub(r'\s+([،؛؟!])', r'\1', text)
        text = re.sub(r'([،؛؟!])([^\s\n])', r'\1 \2', text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _remove_repetition(self, text: str) -> str:
        """إزالة الجمل المكررة المتتالية."""
        lines = text.split('\n')
        seen = set()
        result = []
        for line in lines:
            stripped = line.strip()
            if stripped not in seen or not stripped:
                result.append(line)
                if stripped:
                    seen.add(stripped)
        return '\n'.join(result)

    def _has_code_blocks(self, text: str) -> bool:
        return bool(re.search(r'```|`[^`]+`', text))

    def _has_lists(self, text: str) -> bool:
        return bool(re.search(r'^[\s]*[-*•]\s|^\s*\d+\.\s', text, re.MULTILINE))

    def process(
        self,
        content: str,
        language: Optional[str] = None,
    ) -> PostprocessedResponse:
        """معالجة الاستجابة."""
        original = content
        detected_language = language or self._detect_language(content)

        if self.normalize_ws:
            content = self._normalize_whitespace(content)

        if detected_language == "ar" and self.fix_arabic_punctuation:
            content = self._fix_arabic(content)

        if self.remove_repetition:
            content = self._remove_repetition(content)

        word_count = len(content.split())
        has_code = self._has_code_blocks(content)
        has_lists = self._has_lists(content)

        return PostprocessedResponse(
            content=content,
            original_content=original,
            language=detected_language,
            word_count=word_count,
            has_code=has_code,
            has_lists=has_lists,
        )

    def format_for_display(self, content: str) -> str:
        """تنسيق للعرض في الواجهة."""
        # تحويل URLs إلى روابط
        content = re.sub(
            r'(https?://[^\s\)]+)',
            r'[\1](\1)',
            content,
        )
        return content
