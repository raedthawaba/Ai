from __future__ import annotations

import logging
import os
from typing import AsyncGenerator, List, Dict

from hajeen_platform.core.llm.base import BaseLLMProvider, LLMConfig, LLMRequest, LLMResponse, LLMStreamChunk
from hajeen_platform.hajeen_model.inference.hajeen_provider import HajeenProvider as LegacyHajeenProvider

logger = logging.getLogger(__name__)

class HajeenLLMProvider(BaseLLMProvider):
    """
    مزود LLM لمنصة Hajeen يدمج مع HajeenProvider القديم.
    """
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.legacy_hajeen_provider = LegacyHajeenProvider(model_path=self.config.extra.get("model_path"))
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        logger.info("Initializing HajeenLLMProvider...")
        # The legacy provider has its own lazy loading, so we just mark this as initialized
        self._initialized = True
        logger.info("HajeenLLMProvider initialized.")

    async def _complete_implementation(self, request: LLMRequest) -> LLMResponse:
        """
        تنفيذ inference باستخدام HajeenProvider القديم.
        """
        prompt = " ".join([msg.content for msg in request.messages if msg.role == "user"])
        if not prompt:
            raise ValueError("No user prompt found in the request messages.")

        # The legacy provider returns a string, we need to wrap it in LLMResponse
        legacy_response_content = self.legacy_hajeen_provider.generate(prompt)

        # Placeholder for token counting, as legacy provider doesn't provide it
        prompt_tokens = len(prompt.split())
        completion_tokens = len(legacy_response_content.split())

        return LLMResponse(
            content=legacy_response_content,
            model=self.model_name,
            provider=self.provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            request_id=request.request_id,
        )

    async def _stream_implementation(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        HajeenProvider القديم لا يدعم streaming مباشرة، لذا سنقوم بمحاكاة ذلك.
        """
        response = await self._complete_implementation(request)
        yield LLMStreamChunk(delta=response.content, finish_reason="stop", index=0, model=self.model_name)

    async def health_check(self) -> bool:
        """
        فحص صحة HajeenProvider القديم.
        """
        # For now, we consider it healthy if it can be initialized and doesn't raise an error
        # In a real scenario, this would involve checking model loading status or a simple inference call
        try:
            # Attempt to load the model if not already loaded
            if not self.legacy_hajeen_provider._is_loaded:
                self.legacy_hajeen_provider.load_model()
            return True
        except Exception as e:
            logger.error(f"HajeenProvider health check failed: {e}")
            return False
