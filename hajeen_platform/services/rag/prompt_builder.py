"""Prompt Builder — يبني prompts جاهزة للـ LLM."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from services.rag.context_builder import BuiltContext


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
class BuiltPrompt:
    """prompt مبني وجاهز للـ LLM."""
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


class PromptBuilder:
    """يبني prompts منسّقة للـ LLM."""

    def __init__(self, default_template: PromptTemplate = PromptTemplate.QA_AR):
        self.default_template = default_template

    def build(
        self,
        query: str,
        context: BuiltContext,
        template: Optional[PromptTemplate] = None,
        language: str = "ar",
    ) -> BuiltPrompt:
        tmpl = template or self._select_template(language)
        tmpl_str = _TEMPLATES.get(tmpl, _TEMPLATES[PromptTemplate.QA_AR])
        prompt = tmpl_str.format(
            context=context.formatted_text,
            query=query,
        )
        return BuiltPrompt(
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
