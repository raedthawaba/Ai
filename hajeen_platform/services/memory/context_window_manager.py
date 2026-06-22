"""Phase 8.4 — Context Window Manager: إدارة نافذة السياق للـ LLM."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.llm.base import LLMMessage

logger = logging.getLogger(__name__)


@dataclass
class ContextWindow:
    """نافذة السياق المُهيّأة للإرسال للـ LLM."""
    messages: List[LLMMessage]
    total_tokens: int
    trimmed: bool = False
    messages_dropped: int = 0
    system_preserved: bool = True
    summary_injected: bool = False


class ContextWindowManager:
    """
    إدارة نافذة السياق.

    يضمن أن الرسائل المرسلة للـ LLM لا تتجاوز حد التوكنات،
    مع الحفاظ على أهم الرسائل.

    الاستراتيجيات:
    1. FIFO   — حذف الرسائل الأقدم أولاً
    2. LIFO   — الاحتفاظ بأقدم رسالة + الأحدث
    3. SMART  — تحليل الأهمية والحذف الذكي
    """

    MODEL_CONTEXT_LIMITS = {
        "gpt-3.5-turbo": 4096,
        "gpt-4": 8192,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "llama2": 4096,
        "mistral": 8192,
        "mock-model": 4096,
        "default": 4096,
    }

    def __init__(
        self,
        max_tokens: int = 4096,
        reserved_output_tokens: int = 1024,
        tokens_per_word: float = 1.3,
        strategy: str = "fifo",
    ):
        self.max_tokens = max_tokens
        self.reserved_output = reserved_output_tokens
        self.tokens_per_word = tokens_per_word
        self.strategy = strategy

    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.reserved_output

    def _estimate_tokens(self, text: str) -> int:
        return max(1, int(len(text.split()) * self.tokens_per_word))

    def _message_tokens(self, msg: LLMMessage) -> int:
        # ~4 tokens overhead per message
        return self._estimate_tokens(msg.content) + 4

    def get_model_limit(self, model: Optional[str]) -> int:
        """الحد الأقصى للتوكنات حسب النموذج."""
        if not model:
            return self.MODEL_CONTEXT_LIMITS["default"]
        model_lower = model.lower()
        for key, limit in self.MODEL_CONTEXT_LIMITS.items():
            if key in model_lower:
                return limit
        return self.MODEL_CONTEXT_LIMITS["default"]

    def fit_messages(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> ContextWindow:
        """
        ضبط الرسائل لتناسب نافذة السياق.
        """
        limit = max_tokens or min(
            self.available_tokens,
            self.get_model_limit(model) - self.reserved_output,
        )

        # فصل system message
        system_msgs = [m for m in messages if m.role == "system"]
        other_msgs = [m for m in messages if m.role != "system"]

        system_tokens = sum(self._message_tokens(m) for m in system_msgs)
        budget = limit - system_tokens

        if budget <= 0:
            logger.warning("System prompt alone exceeds token limit!")
            return ContextWindow(
                messages=system_msgs,
                total_tokens=system_tokens,
                trimmed=True,
                messages_dropped=len(other_msgs),
                system_preserved=True,
            )

        # اختيار الرسائل ضمن الميزانية
        selected, dropped, used = self._select_messages(other_msgs, budget)

        final_messages = system_msgs + selected
        total_tokens = system_tokens + used

        if dropped:
            logger.debug(
                "Context trimmed: dropped %d messages (%d tokens available)",
                len(dropped), limit,
            )

        return ContextWindow(
            messages=final_messages,
            total_tokens=total_tokens,
            trimmed=len(dropped) > 0,
            messages_dropped=len(dropped),
            system_preserved=bool(system_msgs),
        )

    def _select_messages(
        self,
        messages: List[LLMMessage],
        budget: int,
    ) -> Tuple[List[LLMMessage], List[LLMMessage], int]:
        """
        اختيار الرسائل ضمن ميزانية التوكنات.
        استراتيجية FIFO: احتفظ بالأحدث.
        """
        selected = []
        used = 0

        for msg in reversed(messages):
            tokens = self._message_tokens(msg)
            if used + tokens <= budget:
                selected.insert(0, msg)
                used += tokens
            else:
                break

        dropped = [m for m in messages if m not in selected]
        return selected, dropped, used

    def inject_summary(
        self,
        messages: List[LLMMessage],
        summary: str,
    ) -> List[LLMMessage]:
        """حقن ملخص للرسائل المحذوفة."""
        summary_msg = LLMMessage(
            role="system",
            content=f"[ملخص المحادثة السابقة]: {summary}",
        )
        result = []
        for msg in messages:
            result.append(msg)
            if msg.role == "system" and result.index(msg) == 0:
                result.append(summary_msg)
        return result if len(result) > len(messages) else [summary_msg] + messages
