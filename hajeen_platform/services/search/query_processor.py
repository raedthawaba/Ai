"""معالجة الاستعلامات قبل البحث الدلالي."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProcessedQuery:
    """الاستعلام بعد المعالجة."""
    original: str
    cleaned: str
    expanded: List[str] = field(default_factory=list)
    language: str = "unknown"
    token_count: int = 0
    is_question: bool = False
    keywords: List[str] = field(default_factory=list)

    @property
    def all_variants(self) -> List[str]:
        """جميع صيغ الاستعلام: الأصلي + الموسّعة."""
        return [self.cleaned] + self.expanded


class QueryProcessor:
    """
    يُعالج الاستعلامات النصية:
    - تنظيف وتطبيع
    - كشف اللغة
    - توسيع الاستعلام (query expansion بسيط)
    - استخراج الكلمات المفتاحية
    """

    _QUESTION_MARKERS_AR = {"ما", "ماذا", "كيف", "لماذا", "متى", "أين", "هل", "من", "أي"}
    _QUESTION_MARKERS_EN = {"what", "how", "why", "when", "where", "who", "which", "is", "are", "can"}

    def process(self, query: str) -> ProcessedQuery:
        cleaned = self._clean(query)
        language = self._detect_language(cleaned)
        is_question = self._is_question(cleaned)
        keywords = self._extract_keywords(cleaned)
        expanded = self._expand(cleaned, language)
        tokens = cleaned.split()
        return ProcessedQuery(
            original=query,
            cleaned=cleaned,
            expanded=expanded,
            language=language,
            token_count=len(tokens),
            is_question=is_question,
            keywords=keywords,
        )

    def _clean(self, text: str) -> str:
        text = text.strip()
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _detect_language(self, text: str) -> str:
        arabic = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
        latin = sum(1 for c in text if c.isalpha() and c.isascii())
        if arabic > latin:
            return "ar"
        if latin > arabic:
            return "en"
        return "mixed"

    def _is_question(self, text: str) -> bool:
        if text.endswith("?") or text.endswith("؟"):
            return True
        first_word = text.split()[0].lower() if text.split() else ""
        return (first_word in self._QUESTION_MARKERS_AR or
                first_word in self._QUESTION_MARKERS_EN)

    def _extract_keywords(self, text: str) -> List[str]:
        stop_ar = {"في", "من", "إلى", "على", "هو", "هي", "عن", "مع", "و", "أو", "لا", "ما"}
        stop_en = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "of"}
        words = re.findall(r"\b[\w\u0600-\u06FF]{3,}\b", text)
        return [w for w in words if w.lower() not in stop_ar | stop_en][:10]

    def _expand(self, text: str, language: str) -> List[str]:
        """توسيع بسيط للاستعلام بمرادفات شائعة."""
        expansions = []
        mappings_ar = {
            "الذكاء الاصطناعي": ["AI", "machine learning", "تعلم الآلة"],
            "تعلم الآلة": ["machine learning", "الذكاء الاصطناعي"],
            "أخبار": ["تقارير", "مستجدات"],
        }
        mappings_en = {
            "artificial intelligence": ["AI", "machine learning", "deep learning"],
            "search": ["retrieval", "query"],
        }
        mappings = mappings_ar if language == "ar" else mappings_en
        for key, synonyms in mappings.items():
            if key.lower() in text.lower():
                expansions.extend(synonyms[:2])
        return expansions[:3]
