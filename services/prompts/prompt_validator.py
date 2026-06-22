"""Phase 8.2 — Prompt Validator: التحقق من صحة الـ prompts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ValidationResult:
    """نتيجة التحقق من prompt."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    token_estimate: int = 0
    language_detected: Optional[str] = None

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class PromptValidator:
    """
    التحقق من صحة الـ prompts قبل الإرسال للـ LLM.

    الفحوصات:
    - الحد الأدنى والأقصى للطول
    - الإدخالات الخطرة (prompt injection)
    - تقدير Token count
    - كشف اللغة
    - التحقق من المتغيرات
    """

    INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"ignore\s+all\s+instructions",
        r"forget\s+everything",
        r"you\s+are\s+now\s+(?:a\s+)?(?:different|new)",
        r"أهمل\s+التعليمات\s+السابقة",
        r"تجاهل\s+جميع\s+التعليمات",
        r"<\|im_end\|>",
        r"<\|system\|>",
        r"\[INST\]",
        r"###\s*Human:",
    ]

    def __init__(
        self,
        min_length: int = 2,
        max_length: int = 50000,
        max_tokens: int = 8000,
        tokens_per_word: float = 1.3,
        check_injection: bool = True,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.max_tokens = max_tokens
        self.tokens_per_word = tokens_per_word
        self.check_injection = check_injection
        self._injection_regex = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * self.tokens_per_word)

    def _detect_language(self, text: str) -> str:
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        latin_chars = len(re.findall(r'[a-zA-Z]', text))
        if arabic_chars > latin_chars:
            return "ar"
        elif latin_chars > 0:
            return "en"
        return "unknown"

    def _check_injection(self, text: str) -> List[str]:
        found = []
        for pattern in self._injection_regex:
            if pattern.search(text):
                found.append(f"Possible prompt injection: '{pattern.pattern[:40]}'")
        return found

    def validate(self, prompt: str) -> ValidationResult:
        """التحقق من صحة prompt."""
        result = ValidationResult(valid=True)

        if not prompt or not prompt.strip():
            result.add_error("Prompt is empty")
            return result

        length = len(prompt)

        if length < self.min_length:
            result.add_error(f"Prompt too short: {length} < {self.min_length}")

        if length > self.max_length:
            result.add_error(
                f"Prompt too long: {length} > {self.max_length} characters"
            )

        token_estimate = self._estimate_tokens(prompt)
        result.token_estimate = token_estimate

        if token_estimate > self.max_tokens:
            result.add_warning(
                f"Token estimate ({token_estimate}) exceeds limit ({self.max_tokens}). "
                "Consider truncating context."
            )

        result.language_detected = self._detect_language(prompt)

        if self.check_injection:
            injection_issues = self._check_injection(prompt)
            for issue in injection_issues:
                result.add_warning(issue)

        if "{" in prompt and "}" in prompt:
            unfilled = re.findall(r'\{(\w+)\}', prompt)
            if unfilled:
                result.add_warning(f"Unfilled template variables: {unfilled}")

        return result

    def validate_messages(self, messages: List[dict]) -> ValidationResult:
        """التحقق من صحة قائمة messages."""
        result = ValidationResult(valid=True)

        if not messages:
            result.add_error("Messages list is empty")
            return result

        valid_roles = {"system", "user", "assistant"}
        total_tokens = 0
        has_user = False

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role not in valid_roles:
                result.add_error(f"Message {i}: invalid role '{role}'")

            if not content:
                result.add_warning(f"Message {i} ({role}) has empty content")

            if role == "user":
                has_user = True

            total_tokens += self._estimate_tokens(content)

        if not has_user:
            result.add_error("No user message found")

        result.token_estimate = total_tokens
        if total_tokens > self.max_tokens:
            result.add_warning(
                f"Total token estimate ({total_tokens}) exceeds limit ({self.max_tokens})"
            )

        return result
