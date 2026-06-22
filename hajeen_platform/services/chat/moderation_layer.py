"""Phase 8.6 — Moderation Layer: طبقة التدقيق والفلترة."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ModerationResult:
    """نتيجة التدقيق."""
    passed: bool
    reason: Optional[str] = None
    flagged_categories: List[str] = field(default_factory=list)
    confidence: float = 1.0

    @classmethod
    def ok(cls) -> "ModerationResult":
        return cls(passed=True)

    @classmethod
    def blocked(cls, reason: str, categories: Optional[List[str]] = None) -> "ModerationResult":
        return cls(
            passed=False,
            reason=reason,
            flagged_categories=categories or [],
        )


class ModerationLayer:
    """
    طبقة التدقيق والفلترة للمدخلات والمخرجات.

    الفحوصات:
    - كلمات محظورة
    - محتوى ضار
    - Prompt injection
    - Hallucination safeguards
    - حماية المعلومات الشخصية
    """

    BLOCKED_PATTERNS = [
        (r'\b(bomb|weapon|hack|exploit|malware|ransomware)\b', "harmful_content"),
        (r'\b(password|credit.?card|ssn|social.security)\s*[:=]\s*\S+', "sensitive_data"),
        (r'ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions', "prompt_injection"),
        (r'<script[^>]*>.*?</script>', "xss"),
        (r'(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+(?:FROM|INTO|TABLE|DATABASE)', "sql_injection"),
    ]

    HALLUCINATION_RESPONSES = [
        "أنا لا أعرف",
        "لا تتوفر لديّ معلومات",
        "I don't know",
        "I'm not sure",
        "I cannot",
    ]

    def __init__(
        self,
        enable_input_check: bool = True,
        enable_output_check: bool = True,
        max_input_length: int = 10000,
        custom_blocked_words: Optional[List[str]] = None,
    ):
        self.enable_input = enable_input_check
        self.enable_output = enable_output_check
        self.max_input_length = max_input_length
        self._patterns = [
            (re.compile(p, re.IGNORECASE | re.DOTALL), cat)
            for p, cat in self.BLOCKED_PATTERNS
        ]
        if custom_blocked_words:
            for word in custom_blocked_words:
                self._patterns.append(
                    (re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE), "custom_block")
                )

    def check_input(self, text: str) -> ModerationResult:
        """فحص المدخلات."""
        if not self.enable_input:
            return ModerationResult.ok()

        if not text or not text.strip():
            return ModerationResult.blocked("Empty input")

        if len(text) > self.max_input_length:
            return ModerationResult.blocked(
                f"Input too long: {len(text)} > {self.max_input_length}",
                ["length_limit"],
            )

        flagged = []
        for pattern, category in self._patterns:
            if pattern.search(text):
                flagged.append(category)

        if flagged:
            return ModerationResult.blocked(
                f"Content flagged: {', '.join(flagged)}",
                flagged,
            )

        return ModerationResult.ok()

    def check_output(self, text: str) -> ModerationResult:
        """فحص المخرجات."""
        if not self.enable_output:
            return ModerationResult.ok()

        # فحص الاستجابات الفارغة
        if not text or not text.strip():
            return ModerationResult.blocked("Empty response from LLM")

        # فحص الاستجابات القصيرة جداً كـ hallucination indicator
        if len(text.strip()) < 5:
            return ModerationResult.blocked(
                "Response too short — possible LLM error",
                ["short_response"],
            )

        return ModerationResult.ok()

    def sanitize_output(self, text: str) -> str:
        """تنظيف المخرجات من المحتوى غير المرغوب."""
        # إزالة HTML tags غير المرغوبة
        text = re.sub(r'<(?!br|p|b|i|strong|em)[^>]+>', '', text)
        # تنظيف المسافات الزائدة
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def add_disclaimer(self, text: str, language: str = "ar") -> str:
        """إضافة تنبيه مناسب للاستجابة."""
        if language == "ar":
            disclaimer = (
                "\n\n⚠️ *تنبيه: هذه المعلومات مقدمة للأغراض العامة فقط، "
                "يرجى التحقق من المصادر الرسمية.*"
            )
        else:
            disclaimer = (
                "\n\n⚠️ *Note: This information is for general purposes only. "
                "Please verify from official sources.*"
            )
        return text + disclaimer
