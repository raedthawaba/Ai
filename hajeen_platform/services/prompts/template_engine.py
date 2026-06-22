"""Phase 8.2 — Template Engine: محرك قوالب الـ prompts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from string import Template
from typing import Any, Dict, List, Optional


@dataclass
class PromptTemplate:
    """قالب Prompt مع metadata."""
    name: str
    template: str
    description: str = ""
    language: str = "ar"
    variables: List[str] = field(default_factory=list)
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.variables:
            self.variables = self._extract_variables()

    def _extract_variables(self) -> List[str]:
        """استخراج المتغيرات من القالب."""
        return re.findall(r'\{(\w+)\}', self.template)

    def render(self, **kwargs: Any) -> str:
        """تطبيق المتغيرات على القالب."""
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    def get_missing_variables(self, provided: Dict[str, Any]) -> List[str]:
        """إيجاد المتغيرات الناقصة."""
        return [v for v in self.variables if v not in provided]


class TemplateEngine:
    """
    محرك قوالب الـ prompts.

    يدير مجموعة من القوالب ويوفر rendering متقدم
    مع دعم متعدد اللغات.
    """

    BUILTIN_TEMPLATES: Dict[str, PromptTemplate] = {}

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """تسجيل القوالب الافتراضية."""
        defaults = [
            PromptTemplate(
                name="rag_qa_ar",
                language="ar",
                description="RAG Question Answering - عربي",
                template=(
                    "أنت مساعد ذكي متخصص. استخدم السياق التالي للإجابة على السؤال.\n\n"
                    "السياق:\n{context}\n\n"
                    "السؤال: {question}\n\n"
                    "الإجابة (باللغة العربية):"
                ),
            ),
            PromptTemplate(
                name="rag_qa_en",
                language="en",
                description="RAG Question Answering - English",
                template=(
                    "You are an intelligent assistant. Use the following context to answer the question.\n\n"
                    "Context:\n{context}\n\n"
                    "Question: {question}\n\n"
                    "Answer:"
                ),
            ),
            PromptTemplate(
                name="summarize_ar",
                language="ar",
                description="تلخيص النصوص",
                template=(
                    "لخّص النص التالي في {max_sentences} جمل أو أقل:\n\n"
                    "{text}\n\n"
                    "الملخص:"
                ),
            ),
            PromptTemplate(
                name="chat_system_ar",
                language="ar",
                description="System prompt للمحادثة",
                template=(
                    "أنت {assistant_name}، مساعد ذكي اصطناعي متخصص في {domain}. "
                    "تتحدث باللغة العربية بأسلوب {tone}. "
                    "التاريخ الحالي: {current_date}."
                ),
            ),
            PromptTemplate(
                name="extraction",
                language="ar",
                description="استخراج المعلومات",
                template=(
                    "من النص التالي، استخرج {entity_type}:\n\n"
                    "{text}\n\n"
                    "النتائج (JSON):"
                ),
            ),
            PromptTemplate(
                name="code_assistant",
                language="en",
                description="Code assistant prompt",
                template=(
                    "You are an expert {language} developer. "
                    "Help with the following task:\n\n{task}\n\n"
                    "Code context:\n```{language}\n{code}\n```\n\n"
                    "Response:"
                ),
            ),
        ]
        for template in defaults:
            self._templates[template.name] = template

    def register(self, template: PromptTemplate) -> None:
        """تسجيل قالب جديد."""
        self._templates[template.name] = template

    def get(self, name: str) -> Optional[PromptTemplate]:
        """استرجاع قالب بالاسم."""
        return self._templates.get(name)

    def get_or_raise(self, name: str) -> PromptTemplate:
        template = self.get(name)
        if template is None:
            raise KeyError(f"Template '{name}' not found. Available: {self.list_templates()}")
        return template

    def render(self, template_name: str, **variables: Any) -> str:
        """تطبيق متغيرات على قالب."""
        template = self.get_or_raise(template_name)
        return template.render(**variables)

    def list_templates(self, language: Optional[str] = None) -> List[str]:
        """قائمة القوالب المتاحة."""
        if language:
            return [
                name for name, t in self._templates.items()
                if t.language == language
            ]
        return list(self._templates.keys())

    def create_custom(
        self,
        name: str,
        template_str: str,
        language: str = "ar",
        description: str = "",
        **kwargs,
    ) -> PromptTemplate:
        """إنشاء وتسجيل قالب مخصص."""
        template = PromptTemplate(
            name=name,
            template=template_str,
            language=language,
            description=description,
            **kwargs,
        )
        self.register(template)
        return template
