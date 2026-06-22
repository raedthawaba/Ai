"""Phase 8.1 — OpenAI Provider: مزود OpenAI / ChatGPT."""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from ..base import (
    BaseLLMProvider,
    LLMConfig,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    مزود OpenAI يدعم:
    - GPT-3.5-turbo, GPT-4, GPT-4o
    - Async inference
    - Token streaming
    - Custom API base (لـ Azure OpenAI / OpenRouter)
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Optional[object] = None

    async def initialize(self) -> None:
        try:
            import openai
            kwargs: dict = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.api_base:
                kwargs["base_url"] = self.config.api_base
            self._client = openai.AsyncOpenAI(**kwargs)
            self._initialized = True
            logger.info("OpenAI provider initialized (model=%s)", self.config.model)
        except ImportError:
            raise ImportError("openai package required: pip install openai")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._client:
            await self.initialize()

        try:
            import openai
            response = await self._client.chat.completions.create(
                model=request.model or self.config.model,
                messages=request.to_messages_list(),
                temperature=request.temperature or self.config.temperature,
                max_tokens=request.max_tokens or self.config.max_tokens,
                top_p=self.config.top_p,
                stream=False,
            )
            choice = response.choices[0]
            usage = response.usage

            return LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                provider=self.provider_name,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                finish_reason=choice.finish_reason or "stop",
                request_id=request.request_id,
            )
        except Exception as e:
            raise LLMProviderError(f"OpenAI error: {e}")

    async def stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        if not self._client:
            await self.initialize()

        try:
            import openai
            stream = await self._client.chat.completions.create(
                model=request.model or self.config.model,
                messages=request.to_messages_list(),
                temperature=request.temperature or self.config.temperature,
                max_tokens=request.max_tokens or self.config.max_tokens,
                stream=True,
            )
            index = 0
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield LLMStreamChunk(
                        delta=delta.content,
                        finish_reason=chunk.choices[0].finish_reason,
                        index=index,
                        model=chunk.model,
                    )
                    index += 1
        except Exception as e:
            raise LLMProviderError(f"OpenAI streaming error: {e}")

    async def health_check(self) -> bool:
        try:
            from ..base import LLMMessage
            req = LLMRequest(
                messages=[LLMMessage(role="user", content="Say 'ok'")],
                max_tokens=5,
            )
            response = await self.complete(req)
            return len(response.content) > 0
        except Exception as e:
            logger.warning("OpenAI health check failed: %s", e)
            return False
