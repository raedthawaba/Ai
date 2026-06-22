"""Phase 8.2 — Prompt Builder: بناء prompts احترافية جاهزة للـ inference."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm.base import LLMMessage, LLMRequest
from .context_injector import ContextInjector
from .system_prompt_manager import SystemPromptManager
from .template_engine import TemplateEngine
from .prompt_validator import PromptValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class BuiltPrompt:
    """Prompt مبني وجاهز للـ inference."""
    messages: List[LLMMessage]
    system_prompt: str
    user_prompt: str
    context_injected: bool
    token_estimate: int
    validation: Optional[ValidationResult] = None
    template_used: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_request(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        session_id: Optional[str] = None,
    ) -> LLMRequest:
        """تحويل إلى LLMRequest جاهز للإرسال."""
        return LLMRequest(
            messages=self.messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            session_id=session_id,
        )


class PromptBuilder:
    """
    بناء prompts احترافية متكاملة.

    يجمع:
    - System prompt من SystemPromptManager
    - Context من ContextInjector (RAG)
    - Template من TemplateEngine
    - Validation من PromptValidator
    - History من conversation
    """

    def __init__(
        self,
        template_engine: Optional[TemplateEngine] = None,
        context_injector: Optional[ContextInjector] = None,
        system_prompt_manager: Optional[SystemPromptManager] = None,
        validator: Optional[PromptValidator] = None,
        max_history_messages: int = 10,
    ):
        self.templates = template_engine or TemplateEngine()
        self.injector = context_injector or ContextInjector()
        self.system_manager = system_prompt_manager or SystemPromptManager()
        self.validator = validator or PromptValidator()
        self.max_history = max_history_messages

    def build_rag_prompt(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        language: str = "ar",
        system_prompt_name: Optional[str] = None,
        history: Optional[List[LLMMessage]] = None,
        max_context_tokens: int = 2000,
        validate: bool = True,
    ) -> BuiltPrompt:
        """
        بناء RAG prompt كامل.

        التدفق:
        1. System prompt
        2. History (اختياري)
        3. Context injection
        4. User question
        """
        # 1. System prompt
        sp_name = system_prompt_manager_name = (
            system_prompt_name or
            ("rag_assistant_ar" if language == "ar" else "default_en")
        )
        system_content = self.system_manager.get_content(sp_name)

        # 2. Inject context
        injected = self.injector.inject(
            context_chunks,
            query=question,
            max_tokens=max_context_tokens,
        )

        # 3. Build user message
        template_name = f"rag_qa_{language}"
        try:
            user_content = self.templates.render(
                template_name,
                context=injected.text,
                question=question,
            )
        except KeyError:
            user_content = (
                f"السياق:\n{injected.text}\n\nالسؤال: {question}"
                if language == "ar"
                else f"Context:\n{injected.text}\n\nQuestion: {question}"
            )
            template_name = "custom"

        # 4. Build messages
        messages: List[LLMMessage] = [
            LLMMessage(role="system", content=system_content)
        ]

        if history:
            trimmed_history = history[-(self.max_history):]
            messages.extend(trimmed_history)

        messages.append(LLMMessage(role="user", content=user_content))

        token_estimate = sum(
            self.validator._estimate_tokens(m.content) for m in messages
        )

        # 5. Validate
        validation = None
        if validate:
            msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
            validation = self.validator.validate_messages(msg_dicts)
            if not validation.valid:
                logger.warning("Prompt validation issues: %s", validation.errors)

        return BuiltPrompt(
            messages=messages,
            system_prompt=system_content,
            user_prompt=user_content,
            context_injected=injected.source_count > 0,
            token_estimate=token_estimate,
            validation=validation,
            template_used=template_name,
            metadata={
                "context_sources": injected.source_count,
                "context_truncated": injected.truncated,
                "language": language,
            },
        )

    def build_chat_prompt(
        self,
        user_message: str,
        history: Optional[List[LLMMessage]] = None,
        system_prompt_name: Optional[str] = None,
        language: str = "ar",
        additional_context: Optional[str] = None,
    ) -> BuiltPrompt:
        """بناء chat prompt بسيط."""
        system_content = self.system_manager.get_content(
            system_prompt_name or ("default_ar" if language == "ar" else "default_en")
        )

        messages: List[LLMMessage] = [
            LLMMessage(role="system", content=system_content)
        ]

        if history:
            messages.extend(history[-(self.max_history):])

        if additional_context:
            user_content = f"{additional_context}\n\n{user_message}"
        else:
            user_content = user_message

        messages.append(LLMMessage(role="user", content=user_content))

        token_estimate = sum(
            self.validator._estimate_tokens(m.content) for m in messages
        )

        return BuiltPrompt(
            messages=messages,
            system_prompt=system_content,
            user_prompt=user_content,
            context_injected=additional_context is not None,
            token_estimate=token_estimate,
            template_used="chat",
            metadata={"language": language},
        )

    def build_completion_prompt(
        self,
        text: str,
        instruction: Optional[str] = None,
        language: str = "ar",
    ) -> BuiltPrompt:
        """بناء completion prompt."""
        if instruction:
            user_content = f"{instruction}\n\n{text}"
        else:
            user_content = text

        messages = [LLMMessage(role="user", content=user_content)]
        return BuiltPrompt(
            messages=messages,
            system_prompt="",
            user_prompt=user_content,
            context_injected=False,
            token_estimate=self.validator._estimate_tokens(user_content),
            template_used="completion",
            metadata={"language": language},
        )
