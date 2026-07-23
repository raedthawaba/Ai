"""
RAG Prompt Builder — يبني prompts جاهزة للـ LLM مع RAG
=========================================================
يرث من AbstractPromptBuilder ويضيف قوالب RAG خاصة.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from hajeen_platform.core.prompts.base import AbstractPromptBuilder, BuiltPrompt as BaseBuiltPrompt
from services.rag.context_builder import BuiltContext

logger = logging.getLogger(__name__)


class PromptTemplate(str, Enum):
    QA_AR = "qa_arabic"
    QA_EN = "qa_english"
    SUMMARIZE = "summarize"
    EXTRACT = "extract"


_TEMPLATES = {
    PromptTemplate.QA_AR: """\
أنت مساعد ذكي متخصص في الإجابة على الأسئلة بناءً على السياق المقدّم.

**السياق:**
{context}

**السؤال:**
{query}

**التعليمات:**
- أجب بناءً على السياق فقط
- إذا لم تجد الإجابة في السياق، قل "لا تتوفر هذه المعلومات في السياق"
- استشهد بالمصادر برقمها [1], [2]...

**الإجابة:**""",

    PromptTemplate.QA_EN: """\
You are an intelligent assistant that answers questions based on the provided context.

**Context:**
{context}

**Question:**
{query}

**Instructions:**
- Answer based solely on the context
- If the answer is not in the context, say "This information is not available in the context"
- Cite sources using their numbers [1], [2]...

**Answer:**""",

    PromptTemplate.SUMMARIZE: """\
لخّص المحتوى التالي بإيجاز مع الحفاظ على النقاط الأساسية:

{context}

الموضوع: {query}

الملخص:""",

    PromptTemplate.EXTRACT: """\
استخرج المعلومات المتعلقة بـ "{query}" من النص التالي:

{context}

المعلومات المستخرجة:""",
}


@dataclass
class RAGBuiltPrompt:
    """prompt مبني وجاهز للـ LLM — RAG specific."""
    prompt: str
    template_used: str
    query: str
    context_chars: int
    estimated_tokens: int

    def to_dict(self) -> dict:
        return {
            "template_used": self.template_used,
            "estimated_tokens": self.estimated_tokens,
            "prompt_preview": self.prompt[:500],
        }


class PromptBuilder(AbstractPromptBuilder):
    """
    يبني prompts منسّقة للـ LLM مع RAG.
    يرث من AbstractPromptBuilder للتوافق مع المنصة الموحّدة.
    """

    def __init__(self, default_template: PromptTemplate = PromptTemplate.QA_AR, max_context_tokens: int = 3500):
        super().__init__(max_context_tokens=max_context_tokens)
        self.default_template = default_template
        logger.info("RAG PromptBuilder initialized with template=%s", default_template.value)

    # ── AbstractPromptBuilder implementation ──────────────────────────────

    def build(self, user_input: str, **kwargs: Any) -> BaseBuiltPrompt:
        """
        Implementation of abstract build() — delegates to RAG build.

        kwargs expected:
          - context: BuiltContext
          - template: Optional[PromptTemplate]
          - language: str = "ar"
        """
        context = kwargs.get("context")
        if context is None:
            # Fallback: treat user_input as query with empty context
            from services.rag.context_builder import BuiltContext
            context = BuiltContext(formatted_text="", chunks=[], total_tokens_estimate=0)

        rag_prompt = self.build_rag(
            query=user_input,
            context=context,
            template=kwargs.get("template"),
            language=kwargs.get("language", "ar"),
        )

        # Convert RAGBuiltPrompt to BaseBuiltPrompt for unified interface
        return BaseBuiltPrompt(
            text=rag_prompt.prompt,
            system_prompt=None,
            messages=[{"role": "user", "content": rag_prompt.prompt}],
            estimated_tokens=rag_prompt.estimated_tokens,
            metadata={
                "type": "rag",
                "template_used": rag_prompt.template_used,
                "query": rag_prompt.query,
                "context_chars": rag_prompt.context_chars,
            }
        )

    # ── RAG-specific methods ──────────────────────────────────────────────

    def build_rag(
        self,
        query: str,
        context: BuiltContext,
        template: Optional[PromptTemplate] = None,
        language: str = "ar",
    ) -> RAGBuiltPrompt:
        """بناء prompt RAG من قالب."""
        tmpl = template or self._select_template(language)
        tmpl_str = _TEMPLATES.get(tmpl, _TEMPLATES[PromptTemplate.QA_AR])
        prompt = tmpl_str.format(
            context=context.formatted_text,
            query=query,
        )
        return RAGBuiltPrompt(
            prompt=prompt,
            template_used=tmpl.value if isinstance(tmpl, PromptTemplate) else str(tmpl),
            query=query,
            context_chars=len(context.formatted_text),
            estimated_tokens=context.total_tokens_estimate + len(query.split()),
        )

    def _select_template(self, language: str) -> PromptTemplate:
        if language == "ar":
            return PromptTemplate.QA_AR
        return PromptTemplate.QA_EN
