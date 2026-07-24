"""
UnifiedPromptBuilder — بناء الـ Prompts الموحّد
=================================================
المصدر الوحيد لبناء جميع أنواع الـ Prompts في منصة Hajeen AI.

يدعم:
- Chat prompts
- RAG prompts
- Agent prompts
- Reasoning prompts
- Tool prompts
- Completion prompts

المبدأ الأساسي:
يمنع وجود أي PromptBuilder مستقل خارج هذا الكلاس.
جميع المكونات القديمة (ChatPromptBuilder, RAGPromptBuilder, ServicePromptBuilder)
أصبحت تستخدم هذا الكلاس مباشرةً.

المسار الرسمي:
  Brain
  ↓
  UnifiedPromptBuilder
  ↓
  ModelRouter → LLM
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.prompts.base import AbstractPromptBuilder, BuiltPrompt

logger = logging.getLogger(__name__)


class PromptMode(str, Enum):
    """أنواع الـ Prompts المدعومة."""
    CHAT = "chat"
    RAG = "rag"
    AGENT = "agent"
    REASONING = "reasoning"
    TOOL = "tool"
    COMPLETION = "completion"


class UnifiedPromptBuilder(AbstractPromptBuilder):
    """
    بناء الـ Prompts الموحّد — نقطة الدخول الوحيدة لبناء أي Prompt.

    يجمع وظائف:
    - core/prompts/prompt_builder.py       → Chat & RAG
    - services/prompts/prompt_builder.py   → Service-level Chat
    - services/rag/prompt_builder.py       → RAG-specific

    لا تحتاج أي مكوّن لاستيراد PromptBuilder من مكان آخر.
    """

    VERSION = "1.0.0"

    # System prompts الافتراضية للغة العربية
    _SYSTEM_PROMPTS: Dict[str, str] = {
        "default": (
            "أنت مساعد ذكاء اصطناعي متقدم من منصة Hajeen AI. "
            "تجيب بدقة وإيجاز، مع الحرص على الفائدة والصدق."
        ),
        "rag_assistant": (
            "أنت مساعد ذكي متخصص في الإجابة على الأسئلة بناءً على السياق المقدّم. "
            "أجب بناءً على السياق فقط. إذا لم تجد الإجابة، قل ذلك صراحةً."
        ),
        "reasoning": (
            "أنت مساعد تحليلي. فكّر خطوة بخطوة قبل الإجابة. "
            "اعرض تفكيرك ثم قدّم الإجابة النهائية."
        ),
        "agent": (
            "أنت وكيل ذكي قادر على استخدام الأدوات المتاحة. "
            "حلّل المهمة، اختر الأداة المناسبة، ونفّذ بدقة."
        ),
        "tool": (
            "أنت مساعد تقني. استخدم الأدوات المتاحة بكفاءة "
            "وأعط النتائج بصيغة منظّمة."
        ),
    }

    # قوالب RAG
    _RAG_TEMPLATE_AR = """السياق المتاح:
{context}

السؤال: {question}

التعليمات:
- أجب بناءً على السياق أعلاه فقط
- إذا لم تتوفر الإجابة في السياق، قل ذلك بوضوح
- استشهد بالمصادر برقمها [1], [2]... عند الإمكان

الإجابة:"""

    _RAG_TEMPLATE_EN = """Available Context:
{context}

Question: {question}

Instructions:
- Answer based solely on the context above
- If the answer is not in the context, say so clearly
- Cite sources by number [1], [2]... when possible

Answer:"""

    def __init__(
        self,
        default_language: str = "ar",
        max_context_tokens: int = 3500,
        model_format: str = "chatml",
    ) -> None:
        super().__init__(max_context_tokens=max_context_tokens)
        self.default_language = default_language
        self.model_format = model_format
        logger.info(
            "UnifiedPromptBuilder v%s initialized (lang=%s, format=%s)",
            self.VERSION, default_language, model_format,
        )

    # ── Core Abstract Method Implementation ───────────────────────────────

    def build(self, user_input: str, **kwargs: Any) -> BuiltPrompt:
        """
        بناء Prompt بناءً على النمط المطلوب.

        kwargs:
          mode (PromptMode): نوع الـ Prompt (افتراضي: CHAT)
          history (List[Dict]): سجل المحادثة
          system_prompt (str): System prompt مخصص
          context (str | List): سياق RAG
          language (str): اللغة (ar|en)
          tools (List[Dict]): الأدوات للـ Agent
          strategy (str): استراتيجية التفكير للـ Reasoning
        """
        mode = kwargs.get("mode", PromptMode.CHAT)

        if mode == PromptMode.RAG:
            context = kwargs.get("context", "")
            if isinstance(context, list):
                context = "\n\n".join(
                    f"[{i+1}] {c}" for i, c in enumerate(context)
                )
            return self.build_rag(
                query=user_input,
                context=context,
                history=kwargs.get("history"),
                language=kwargs.get("language", self.default_language),
            )

        if mode == PromptMode.AGENT:
            return self.build_agent(
                task=user_input,
                tools=kwargs.get("tools", []),
                context=kwargs.get("context"),
            )

        if mode == PromptMode.REASONING:
            return self.build_reasoning(
                problem=user_input,
                strategy=kwargs.get("strategy", "chain_of_thought"),
                context=kwargs.get("context"),
            )

        if mode == PromptMode.TOOL:
            return self._build_tool_prompt(user_input, **kwargs)

        if mode == PromptMode.COMPLETION:
            return self._build_completion_prompt(user_input, **kwargs)

        # Default: CHAT
        return self.build_chat(
            user_message=user_input,
            history=kwargs.get("history"),
            system_prompt=kwargs.get("system_prompt"),
        )

    # ── Chat Prompt ────────────────────────────────────────────────────────

    def build_chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        language: str = "ar",
        **kwargs: Any,
    ) -> BuiltPrompt:
        """
        بناء Chat Prompt كامل.

        المسار:
          System Prompt → History (trimmed) → User Message
        """
        system_text = system_prompt or self._SYSTEM_PROMPTS["default"]
        messages = [{"role": "system", "content": system_text}]

        if history:
            # تقليص التاريخ ليناسب حد التوكنات
            trimmed = self._trim_history(history, max_messages=20)
            messages.extend(trimmed)

        messages.append({"role": "user", "content": user_message})

        text = self._format_messages(messages)
        return BuiltPrompt(
            text=text,
            system_prompt=system_text,
            messages=messages,
            estimated_tokens=self.estimate_tokens(text),
            metadata={"type": "chat", "language": language},
        )

    # ── RAG Prompt ─────────────────────────────────────────────────────────

    def build_rag(
        self,
        query: str,
        context: str,
        history: Optional[List[Dict[str, str]]] = None,
        language: str = "ar",
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> BuiltPrompt:
        """
        بناء RAG Prompt مع سياق المصادر.

        المسار:
          System (RAG) → History → Context + Question
        """
        system_text = system_prompt or self._SYSTEM_PROMPTS["rag_assistant"]

        template = self._RAG_TEMPLATE_AR if language == "ar" else self._RAG_TEMPLATE_EN
        user_content = template.format(
            context=self.trim_to_fit(context, max_tokens=self.max_context_tokens - 500),
            question=query,
        )

        messages = [{"role": "system", "content": system_text}]
        if history:
            messages.extend(self._trim_history(history, max_messages=10))
        messages.append({"role": "user", "content": user_content})

        text = self._format_messages(messages)
        return BuiltPrompt(
            text=text,
            system_prompt=system_text,
            messages=messages,
            estimated_tokens=self.estimate_tokens(text),
            metadata={
                "type": "rag",
                "language": language,
                "context_chars": len(context),
                "query": query,
            },
        )

    # ── Agent Prompt ───────────────────────────────────────────────────────

    def build_agent(
        self,
        task: str,
        tools: List[Dict[str, Any]],
        context: Optional[str] = None,
        **kwargs: Any,
    ) -> BuiltPrompt:
        """بناء Agent Prompt مع قائمة الأدوات."""
        system_text = self._SYSTEM_PROMPTS["agent"]
        tool_desc = "\n".join([
            f"- **{t.get('name', 'tool')}**: {t.get('description', '')}"
            for t in tools
        ])

        user_content = f"المهمة: {task}"
        if tool_desc:
            user_content += f"\n\nالأدوات المتاحة:\n{tool_desc}"
        if context:
            user_content += f"\n\nسياق إضافي:\n{context}"
        user_content += "\n\nنفّذ المهمة باستخدام الأدوات المتاحة."

        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_content},
        ]
        text = self._format_messages(messages)
        return BuiltPrompt(
            text=text,
            system_prompt=system_text,
            messages=messages,
            estimated_tokens=self.estimate_tokens(text),
            metadata={"type": "agent", "tools": [t.get("name") for t in tools]},
        )

    # ── Reasoning Prompt ───────────────────────────────────────────────────

    def build_reasoning(
        self,
        problem: str,
        strategy: str = "chain_of_thought",
        context: Optional[str] = None,
        **kwargs: Any,
    ) -> BuiltPrompt:
        """بناء Reasoning Prompt مع استراتيجية التفكير."""
        strategies = {
            "chain_of_thought": "فكّر خطوة بخطوة قبل الإجابة. اعرض كل خطوة بوضوح.",
            "tree_of_thought": "استكشف مسارات تفكير متعددة ثم اختر الأفضل.",
            "self_consistency": "فكّر بطرق متعددة ثم اختر الإجابة الأكثر اتساقاً.",
        }
        strategy_text = strategies.get(strategy, strategies["chain_of_thought"])
        system_text = self._SYSTEM_PROMPTS["reasoning"]

        user_content = f"{strategy_text}\n\nالمسألة: {problem}"
        if context:
            user_content += f"\n\nمعلومات مفيدة:\n{context}"
        user_content += "\n\nأظهر تفكيرك ثم قدّم الإجابة النهائية."

        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_content},
        ]
        text = self._format_messages(messages)
        return BuiltPrompt(
            text=text,
            system_prompt=system_text,
            messages=messages,
            estimated_tokens=self.estimate_tokens(text),
            metadata={"type": "reasoning", "strategy": strategy},
        )

    # ── Private Helpers ────────────────────────────────────────────────────

    def _build_tool_prompt(self, user_input: str, **kwargs: Any) -> BuiltPrompt:
        """بناء Tool Prompt."""
        system_text = self._SYSTEM_PROMPTS["tool"]
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_input},
        ]
        text = self._format_messages(messages)
        return BuiltPrompt(
            text=text,
            system_prompt=system_text,
            messages=messages,
            estimated_tokens=self.estimate_tokens(text),
            metadata={"type": "tool"},
        )

    def _build_completion_prompt(self, prefix: str, **kwargs: Any) -> BuiltPrompt:
        """بناء Completion Prompt."""
        return BuiltPrompt(
            text=prefix,
            system_prompt=None,
            messages=[{"role": "user", "content": prefix}],
            estimated_tokens=self.estimate_tokens(prefix),
            metadata={"type": "completion"},
        )

    def _trim_history(
        self,
        history: List[Dict[str, str]],
        max_messages: int = 20,
    ) -> List[Dict[str, str]]:
        """تقليص التاريخ للرسائل الأحدث."""
        return history[-max_messages:] if len(history) > max_messages else history

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """تحويل الرسائل لنص حسب صيغة النموذج."""
        fmt = self.model_format.lower()
        if fmt == "llama3":
            return self._to_llama3(messages)
        if fmt == "mistral":
            return self._to_mistral(messages)
        return self._to_chatml(messages)

    def _to_chatml(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def _to_llama3(self, messages: List[Dict[str, str]]) -> str:
        parts = ["<|begin_of_text|>"]
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>")
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return "\n".join(parts)

    def _to_mistral(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("user", "system"):
                parts.append(f"[INST] {content} [/INST]")
            else:
                parts.append(content)
        return "\n".join(parts)


# ── Singleton Management ───────────────────────────────────────────────────

_unified_builder: Optional[UnifiedPromptBuilder] = None


def get_unified_prompt_builder(
    language: str = "ar",
    max_context_tokens: int = 3500,
) -> UnifiedPromptBuilder:
    """الحصول على نسخة Singleton من UnifiedPromptBuilder."""
    global _unified_builder
    if _unified_builder is None:
        _unified_builder = UnifiedPromptBuilder(
            default_language=language,
            max_context_tokens=max_context_tokens,
        )
    return _unified_builder
