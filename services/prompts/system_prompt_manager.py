"""Phase 8.2 — System Prompt Manager: إدارة system prompts."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SystemPrompt:
    """System prompt جاهز للاستخدام."""
    name: str
    content: str
    language: str = "ar"
    persona: str = "assistant"
    domain: str = "general"
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)


class SystemPromptManager:
    """
    مدير System Prompts.

    يوفر system prompts جاهزة لسيناريوهات متعددة
    مع دعم التخصيص الديناميكي.
    """

    def __init__(self):
        self._prompts: Dict[str, SystemPrompt] = {}
        self._active_prompt: Optional[str] = None
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            SystemPrompt(
                name="default_ar",
                language="ar",
                content=(
                    "أنت مساعد ذكاء اصطناعي متطور تعمل ضمن منصة هجين. "
                    "تتحدث باللغة العربية بأسلوب واضح ومفيد. "
                    "تُقدّم إجابات دقيقة وموثوقة مع الإشارة إلى المصادر عند توفرها. "
                    "لا تُقدّم معلومات مضللة ولا تتجاوز نطاق معرفتك."
                ),
                persona="assistant",
                domain="general",
                tags=["default", "arabic"],
            ),
            SystemPrompt(
                name="rag_assistant_ar",
                language="ar",
                content=(
                    "أنت مساعد بحثي متخصص في منصة هجين للذكاء الاصطناعي. "
                    "مهمتك الإجابة على الأسئلة استناداً إلى السياق المقدم. "
                    "إذا لم تجد المعلومات في السياق، قل ذلك بصراحة. "
                    "اذكر أرقام المصادر [1], [2] ... عند الاستشهاد بها. "
                    "تحدث دائماً بالعربية الفصحى الواضحة."
                ),
                persona="research_assistant",
                domain="rag",
                tags=["rag", "arabic", "citations"],
            ),
            SystemPrompt(
                name="tech_expert_ar",
                language="ar",
                content=(
                    "أنت خبير تقني في مجال الذكاء الاصطناعي وعلوم البيانات. "
                    "تُقدّم تفسيرات تقنية دقيقة مع أمثلة عملية. "
                    "تستخدم المصطلحات التقنية الصحيحة مع شرح مبسط عند الحاجة."
                ),
                persona="tech_expert",
                domain="technology",
                tags=["tech", "ai", "arabic"],
            ),
            SystemPrompt(
                name="default_en",
                language="en",
                content=(
                    "You are an advanced AI assistant on the Hajeen platform. "
                    "You provide accurate, helpful, and concise responses. "
                    "You cite sources when available and acknowledge uncertainty honestly."
                ),
                persona="assistant",
                domain="general",
                tags=["default", "english"],
            ),
            SystemPrompt(
                name="coding_assistant",
                language="en",
                content=(
                    "You are an expert software engineer and coding assistant. "
                    "You write clean, efficient, well-documented code. "
                    "You explain your reasoning and suggest best practices."
                ),
                persona="coding_assistant",
                domain="software",
                tags=["coding", "technical"],
            ),
        ]
        for sp in defaults:
            self._prompts[sp.name] = sp
        self._active_prompt = "default_ar"

    def register(self, prompt: SystemPrompt) -> None:
        """تسجيل system prompt جديد."""
        self._prompts[prompt.name] = prompt

    def get(self, name: str) -> Optional[SystemPrompt]:
        return self._prompts.get(name)

    def get_content(self, name: Optional[str] = None) -> str:
        """استرجاع محتوى system prompt."""
        prompt_name = name or self._active_prompt or "default_ar"
        prompt = self.get(prompt_name)
        if prompt is None:
            return self._prompts.get("default_ar", SystemPrompt(
                name="fallback", content="You are a helpful assistant."
            )).content
        return prompt.content

    def set_active(self, name: str) -> None:
        """تعيين system prompt النشط."""
        if name not in self._prompts:
            raise KeyError(f"System prompt '{name}' not found")
        self._active_prompt = name

    def build_dynamic(
        self,
        base_name: str = "default_ar",
        assistant_name: str = "هجين",
        domain: str = "الذكاء الاصطناعي",
        additional_instructions: Optional[str] = None,
        include_date: bool = True,
    ) -> str:
        """بناء system prompt ديناميكي."""
        base = self.get_content(base_name)
        parts = [base]

        if assistant_name:
            parts.append(f"اسمك: {assistant_name}")
        if domain:
            parts.append(f"تخصصك: {domain}")
        if include_date:
            today = datetime.date.today().strftime("%Y-%m-%d")
            parts.append(f"التاريخ الحالي: {today}")
        if additional_instructions:
            parts.append(additional_instructions)

        return "\n".join(parts)

    def list_prompts(self, language: Optional[str] = None) -> List[str]:
        """قائمة System prompts المتاحة."""
        from typing import List
        if language:
            return [n for n, p in self._prompts.items() if p.language == language]
        return list(self._prompts.keys())
