from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PromptTemplate:
    name: str
    template: str
    variables: List[str] = field(default_factory=list)
    description: str = ""
    max_tokens: int = 4096

    def render(self, **kwargs: Any) -> str:
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def validate_variables(self, **kwargs: Any) -> List[str]:
        missing = [v for v in self.variables if v not in kwargs]
        return missing


class TemplateRegistry:
    """Global registry of named prompt templates."""

    _templates: Dict[str, PromptTemplate] = {}

    @classmethod
    def register(cls, template: PromptTemplate) -> None:
        cls._templates[template.name] = template

    @classmethod
    def get(cls, name: str) -> Optional[PromptTemplate]:
        return cls._templates.get(name)

    @classmethod
    def get_or_raise(cls, name: str) -> PromptTemplate:
        t = cls._templates.get(name)
        if t is None:
            raise KeyError(f"Template '{name}' not found")
        return t

    @classmethod
    def list_templates(cls) -> List[str]:
        return list(cls._templates.keys())


# ── Built-in templates ─────────────────────────────────────────────────────────

TemplateRegistry.register(PromptTemplate(
    name="rag_answer",
    template=(
        "You are a helpful AI assistant. Use the context below to answer the question.\n\n"
        "Context:\n{{context}}\n\n"
        "Question: {{question}}\n\n"
        "Answer:"
    ),
    variables=["context", "question"],
    description="RAG-based Q&A",
))

TemplateRegistry.register(PromptTemplate(
    name="chat",
    template="{{system_prompt}}\n\n{{history}}\nUser: {{user_message}}\nAssistant:",
    variables=["system_prompt", "history", "user_message"],
    description="Multi-turn chat",
))

TemplateRegistry.register(PromptTemplate(
    name="completion",
    template="{{prefix}}",
    variables=["prefix"],
    description="Raw text completion",
))

TemplateRegistry.register(PromptTemplate(
    name="summarize",
    template=(
        "Summarize the following text concisely:\n\n{{text}}\n\nSummary:"
    ),
    variables=["text"],
    description="Text summarization",
))

TemplateRegistry.register(PromptTemplate(
    name="code_gen",
    template=(
        "You are an expert programmer. Write {{language}} code for the following task:\n\n"
        "Task: {{task}}\n\nCode:"
    ),
    variables=["language", "task"],
    description="Code generation",
))

TemplateRegistry.register(PromptTemplate(
    name="instruction",
    template="### Instruction:\n{{instruction}}\n\n### Response:",
    variables=["instruction"],
    description="Alpaca instruction format",
))
