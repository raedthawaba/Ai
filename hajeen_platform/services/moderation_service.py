from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_HARMFUL_PATTERNS = [
    r"\b(how\s+to\s+make\s+(bomb|weapon|poison|drug))",
    r"\b(kill\s+yourself|suicide\s+method)",
    r"\b(child\s+abuse|child\s+porn)",
    r"\b(hack\s+(bank|credit\s+card|password))",
]

_COMPILED_PATTERNS = [re.compile(p, re.I) for p in _HARMFUL_PATTERNS]


@dataclass
class ModerationResult:
    flagged: bool
    categories: List[str] = field(default_factory=list)
    score: float = 0.0
    action: str = "allow"
    reason: Optional[str] = None


class ModerationService:
    """Rule-based + optional LLM-backed content moderation."""

    def __init__(
        self,
        max_input_length: int = 8000,
        block_harmful: bool = True,
        block_pii: bool = False,
    ) -> None:
        self.max_input_length = max_input_length
        self.block_harmful = block_harmful
        self.block_pii = block_pii

    def check(self, text: str) -> ModerationResult:
        categories: List[str] = []
        score = 0.0

        if len(text) > self.max_input_length:
            return ModerationResult(
                flagged=True,
                categories=["length_exceeded"],
                score=1.0,
                action="block",
                reason=f"Input exceeds {self.max_input_length} characters",
            )

        if self.block_harmful:
            for pattern in _COMPILED_PATTERNS:
                if pattern.search(text):
                    categories.append("harmful_content")
                    score = max(score, 0.9)
                    break

        if self.block_pii:
            pii_hit, pii_cats = self._check_pii(text)
            if pii_hit:
                categories.extend(pii_cats)
                score = max(score, 0.5)

        flagged = bool(categories)
        action = "block" if score >= 0.8 else ("warn" if flagged else "allow")
        return ModerationResult(
            flagged=flagged,
            categories=categories,
            score=round(score, 3),
            action=action,
            reason=f"Detected: {', '.join(categories)}" if categories else None,
        )

    def _check_pii(self, text: str) -> Tuple[bool, List[str]]:
        cats: List[str] = []
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
            cats.append("ssn")
        if re.search(r"\b(?:\d{4}[-\s]?){3}\d{4}\b", text):
            cats.append("credit_card")
        if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text):
            cats.append("email")
        return bool(cats), cats

    def is_allowed(self, text: str) -> bool:
        result = self.check(text)
        return result.action != "block"

    def filter_output(self, text: str) -> str:
        result = self.check(text)
        if result.action == "block":
            return "I'm unable to provide that information."
        return text
