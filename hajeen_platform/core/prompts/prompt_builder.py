from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .templates import TemplateRegistry
from .system_prompts import SystemPromptLibrary
from .conversation_formatter import ConversationFormatter, Message, MessageRole

logger = logging.getLogger(__name__)


class PromptBuilder:
    """High-level builder that assembles complete prompts from components."""

    def __init__(
        self,
        model_format: str = "chatml",
        system_persona: str = "default",
        max_context_tokens: int = 3500,
    ) -> None:
        self.model_format = model_format
        self.system_persona = system_persona
        self.max_context_tokens = max_context_tokens
        self._formatter = ConversationFormatter()

    def build_chat(
        self,
        user_message: str,
        history: Optional[List[Message]] = None,
        system_override: Optional[str] = None,
    ) -> str:
        system_text = system_override or SystemPromptLibrary.get(self.system_persona)
        messages: List[Message] = [Message(role=MessageRole.SYSTEM, content=system_text)]
        if history:
            messages.extend(ConversationFormatter.trim_history(history, max_messages=20))
        messages.append(Message(role=MessageRole.USER, content=user_message))

        return self._format(messages)

    def build_rag(
        self,
        question: str,
        context_chunks: List[str],
        history: Optional[List[Message]] = None,
        system_override: Optional[str] = None,
    ) -> str:
        context = "\n\n".join(
            f"[{i + 1}] {chunk}" for i, chunk in enumerate(context_chunks)
        )
        system_text = system_override or SystemPromptLibrary.get("rag_assistant")
        template = TemplateRegistry.get_or_raise("rag_answer")
        user_content = template.render(context=context, question=question)

        messages: List[Message] = [Message(role=MessageRole.SYSTEM, content=system_text)]
        if history:
            messages.extend(ConversationFormatter.trim_history(history, max_messages=10))
        messages.append(Message(role=MessageRole.USER, content=user_content))

        return self._format(messages)

    def build_completion(self, prefix: str) -> str:
        template = TemplateRegistry.get_or_raise("completion")
        return template.render(prefix=prefix)

    def build_instruction(self, instruction: str, input_text: str = "") -> str:
        return ConversationFormatter.to_alpaca(instruction, input_text)

    def build_from_template(self, template_name: str, **kwargs: Any) -> str:
        template = TemplateRegistry.get_or_raise(template_name)
        missing = template.validate_variables(**kwargs)
        if missing:
            raise ValueError(f"Missing template variables: {missing}")
        return template.render(**kwargs)

    def _format(self, messages: List[Message]) -> str:
        fmt = self.model_format.lower()
        if fmt == "llama3":
            return ConversationFormatter.to_llama3(messages)
        if fmt == "mistral":
            return ConversationFormatter.to_mistral(messages)
        return ConversationFormatter.to_chatml(messages)
