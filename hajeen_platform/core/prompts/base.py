"""
Abstract Prompt Builder — الواجهة الموحّدة لبناء الـ Prompts
===============================================================
جميع PromptBuilders في المنصة يجب أن يرثوا من هذه الواجهة.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BuiltPrompt:
    """Prompt مُبنى جاهز للإرسال للنموذج."""
    text: str
    system_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None
    estimated_tokens: int = 0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_request(self) -> Dict[str, Any]:
        """تحويل لصيغة طلب OpenAI-compatible."""
        if self.messages:
            return {
                "messages": self.messages,
                **self.metadata
            }
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": self.text})
        return {"messages": messages, **self.metadata}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "estimated_tokens": self.estimated_tokens,
            "metadata": self.metadata,
        }


class AbstractPromptBuilder(ABC):
    """الواجهة المجردة لجميع Prompt Builders."""

    def __init__(self, max_context_tokens: int = 3500) -> None:
        self.max_context_tokens = max_context_tokens
        logger.info("%s initialized (max_context=%d)", self.__class__.__name__, max_context_tokens)

    # ── Methods that MUST be implemented ──────────────────────────────────

    @abstractmethod
    def build(self, user_input: str, **kwargs: Any) -> BuiltPrompt:
        """بناء prompt أساسي من مدخل المستخدم."""
        ...

    # ── Methods with default implementations ──────────────────────────────

    def build_chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> BuiltPrompt:
        """بناء prompt محادثة."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        text = "\n\n".join([f"{m['role']}: {m['content']}" for m in messages])
        return BuiltPrompt(
            text=text,
            system_prompt=system_prompt,
            messages=messages,
            estimated_tokens=self.estimate_tokens(text),
            metadata={"type": "chat", **kwargs}
        )

    def build_rag(
        self,
        query: str,
        context: str,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any
    ) -> BuiltPrompt:
        """بناء prompt مع سياق RAG."""
        system = kwargs.get("system_prompt", "أنت مساعد ذكي. استخدم السياق التالي للإجابة.")
        prompt_text = f"""السياق:
{context}

السؤال: {query}

أجب بناءً على السياق أعلاه."""
        return self.build_chat(
            user_message=prompt_text,
            history=history,
            system_prompt=system,
            **{**kwargs, "type": "rag"}
        )

    def build_agent(
        self,
        task: str,
        tools: List[Dict[str, Any]],
        context: Optional[str] = None,
        **kwargs: Any
    ) -> BuiltPrompt:
        """بناء prompt للـ Agent."""
        tool_desc = "\n".join([f"- {t['name']}: {t.get('description', '')}" for t in tools])
        prompt_text = f"""المهمة: {task}

الأدوات المتاحة:
{tool_desc}

{context or ''}

نفّذ المهمة باستخدام الأدوات المتاحة."""
        return BuiltPrompt(
            text=prompt_text,
            estimated_tokens=self.estimate_tokens(prompt_text),
            metadata={"type": "agent", "tools": [t['name'] for t in tools], **kwargs}
        )

    def build_reasoning(
        self,
        problem: str,
        strategy: str = "chain_of_thought",
        context: Optional[str] = None,
        **kwargs: Any
    ) -> BuiltPrompt:
        """بناء prompt للاستدلال."""
        strategies = {
            "chain_of_thought": "فكّر خطوة بخطوة قبل الإجابة.",
            "tree_of_thought": "فكّر في عدة مسارات ثم اختر الأفضل.",
            "self_consistency": "أجب بطرق متعددة ثم اختر الأكثر اتساقاً.",
        }
        strategy_text = strategies.get(strategy, strategies["chain_of_thought"])
        prompt_text = f"""{strategy_text}

المسألة: {problem}

{context or ''}

أظهر تفكيرك ثم قدّم الإجابة النهائية."""
        return BuiltPrompt(
            text=prompt_text,
            estimated_tokens=self.estimate_tokens(prompt_text),
            metadata={"type": "reasoning", "strategy": strategy, **kwargs}
        )

    # ── Utility methods ───────────────────────────────────────────────────

    def estimate_tokens(self, text: str) -> int:
        """تقدير عدد التوكنات (تقريبي: 1 token ≈ 0.75 word)."""
        words = len(text.split())
        return int(words / 0.75)

    def validate(self, prompt: BuiltPrompt) -> bool:
        """التحقق من صحة الـ Prompt."""
        if not prompt.text or len(prompt.text.strip()) == 0:
            logger.warning("Prompt validation failed: empty text")
            return False
        if prompt.estimated_tokens > self.max_context_tokens:
            logger.warning("Prompt validation failed: token limit exceeded (%d > %d)",
                         prompt.estimated_tokens, self.max_context_tokens)
            return False
        return True

    def trim_to_fit(self, text: str, max_tokens: Optional[int] = None) -> str:
        """قص النص ليناسب حد التوكنات."""
        limit = max_tokens or self.max_context_tokens
        estimated = self.estimate_tokens(text)
        if estimated <= limit:
            return text
        # Rough trim: keep first 80% of token budget
        target_words = int(limit * 0.75 * 0.8)
        words = text.split()
        trimmed = " ".join(words[:target_words])
        logger.info("Trimmed prompt from ~%d to ~%d tokens", estimated, limit)
        return trimmed + "\n[... تم قص السياق للالتزام بحد التوكنات ...]"

    @property
    def builder_name(self) -> str:
        return self.__class__.__name__
