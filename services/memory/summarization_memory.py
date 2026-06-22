"""Phase 8.4 — Summarization Memory: ذاكرة مع تلخيص تلقائي."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm.base import LLMMessage
from .conversation_memory import ConversationMemory, Message

logger = logging.getLogger(__name__)


@dataclass
class MemorySummary:
    """ملخص جزء من المحادثة."""
    content: str
    messages_summarized: int
    token_estimate: int
    created_at: float = field(default_factory=lambda: __import__('time').time())

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "messages_summarized": self.messages_summarized,
            "token_estimate": self.token_estimate,
            "created_at": self.created_at,
        }


class SummarizationMemory:
    """
    ذاكرة مع تلخيص تلقائي للمحادثات الطويلة.

    عند تجاوز الحد، يُلخّص الرسائل القديمة
    ويحتفظ بالملخص كـ system context.
    """

    SUMMARY_PROMPT_AR = (
        "لخّص المحادثة التالية في 3-5 جمل، مع الاحتفاظ بالمعلومات المهمة:\n\n"
        "{conversation}\n\nالملخص:"
    )
    SUMMARY_PROMPT_EN = (
        "Summarize the following conversation in 3-5 sentences, "
        "keeping key information:\n\n{conversation}\n\nSummary:"
    )

    def __init__(
        self,
        base_memory: Optional[ConversationMemory] = None,
        summarize_threshold: int = 20,
        keep_recent: int = 8,
        language: str = "ar",
    ):
        self.memory = base_memory or ConversationMemory()
        self.summarize_threshold = summarize_threshold
        self.keep_recent = keep_recent
        self.language = language
        self._summaries: List[MemorySummary] = []

    def add_user_message(self, content: str, **kwargs) -> Message:
        msg = self.memory.add_user_message(content, **kwargs)
        self._maybe_summarize()
        return msg

    def add_assistant_message(self, content: str, **kwargs) -> Message:
        msg = self.memory.add_assistant_message(content, **kwargs)
        return msg

    def _maybe_summarize(self) -> None:
        """تلخيص تلقائي إذا تجاوز عدد الرسائل الحد."""
        if self.memory.message_count >= self.summarize_threshold:
            self._create_summary_from_old()

    def _create_summary_from_old(self) -> Optional[MemorySummary]:
        """
        إنشاء ملخص للرسائل القديمة بدون LLM.
        (ملاحظة: في الإنتاج، يُستخدم LLM للتلخيص)
        """
        all_messages = self.memory._messages
        to_summarize = all_messages[:-self.keep_recent]

        if not to_summarize:
            return None

        summary_lines = []
        for msg in to_summarize:
            role_ar = "المستخدم" if msg.role == "user" else "المساعد"
            summary_lines.append(f"{role_ar}: {msg.content[:100]}...")

        summary_text = " | ".join(summary_lines)
        token_estimate = int(len(summary_text.split()) * 1.3)

        summary = MemorySummary(
            content=summary_text,
            messages_summarized=len(to_summarize),
            token_estimate=token_estimate,
        )
        self._summaries.append(summary)

        # الاحتفاظ بالرسائل الحديثة فقط
        self.memory._messages = all_messages[-self.keep_recent:]

        logger.info(
            "Memory summarized: %d messages → summary (%d tokens)",
            len(to_summarize), token_estimate,
        )
        return summary

    async def summarize_with_llm(self, llm_manager: Any) -> Optional[MemorySummary]:
        """تلخيص باستخدام LLM (النسخة الاحترافية)."""
        all_messages = self.memory._messages
        to_summarize = all_messages[:-self.keep_recent]
        if not to_summarize:
            return None

        conversation = "\n".join(
            f"{m.role}: {m.content}" for m in to_summarize
        )

        prompt = (
            self.SUMMARY_PROMPT_AR if self.language == "ar"
            else self.SUMMARY_PROMPT_EN
        ).format(conversation=conversation)

        try:
            request_messages = [{"role": "user", "content": prompt}]
            response = await llm_manager.complete(
                __import__('core.llm.base', fromlist=['LLMRequest']).LLMRequest(
                    messages=[LLMMessage(role="user", content=prompt)],
                    max_tokens=200,
                    temperature=0.3,
                )
            )
            summary_text = response.content.strip()
        except Exception as e:
            logger.warning("LLM summarization failed: %s", e)
            summary_text = f"[ملخص تلقائي لـ {len(to_summarize)} رسائل]"

        token_estimate = int(len(summary_text.split()) * 1.3)
        summary = MemorySummary(
            content=summary_text,
            messages_summarized=len(to_summarize),
            token_estimate=token_estimate,
        )
        self._summaries.append(summary)
        self.memory._messages = all_messages[-self.keep_recent:]
        return summary

    def get_messages(self, include_summaries: bool = True) -> List[LLMMessage]:
        """الحصول على الرسائل مع حقن الملخصات."""
        messages = self.memory.get_messages(include_system=True)
        if include_summaries and self._summaries:
            latest_summary = self._summaries[-1]
            summary_msg = LLMMessage(
                role="system",
                content=f"[سياق المحادثة السابقة]: {latest_summary.content}",
            )
            messages.insert(1, summary_msg)
        return messages

    def get_summaries(self) -> List[Dict]:
        return [s.to_dict() for s in self._summaries]

    @property
    def total_summaries(self) -> int:
        return len(self._summaries)
