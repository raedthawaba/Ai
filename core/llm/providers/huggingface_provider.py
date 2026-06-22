"""Phase 8.1 — HuggingFace Provider: مزود HuggingFace Inference API."""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

import httpx

from ..base import (
    BaseLLMProvider,
    LLMConfig,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)

logger = logging.getLogger(__name__)

HF_API_URL = "https://api-inference.huggingface.co/models"


class HuggingFaceProvider(BaseLLMProvider):
    """
    مزود HuggingFace Inference API.

    يدعم:
    - Text generation models
    - Async HTTP requests
    - Streaming عبر SSE
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._base_url = config.api_base or HF_API_URL
        self._headers: dict = {}

    async def initialize(self) -> None:
        self._headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            self._headers["Authorization"] = f"Bearer {self.config.api_key}"
        self._initialized = True
        logger.info("HuggingFace provider initialized (model=%s)", self.config.model)

    async def _build_prompt(self, request: LLMRequest) -> str:
        """بناء prompt من messages."""
        parts = []
        for msg in request.messages:
            if msg.role == "system":
                parts.append(f"System: {msg.content}")
            elif msg.role == "user":
                parts.append(f"Human: {msg.content}")
            elif msg.role == "assistant":
                parts.append(f"Assistant: {msg.content}")
        parts.append("Assistant:")
        return "\n".join(parts)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._initialized:
            await self.initialize()

        model = request.model or self.config.model
        url = f"{self._base_url}/{model}"
        prompt = await self._build_prompt(request)

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": request.temperature or self.config.temperature,
                "max_new_tokens": request.max_tokens or self.config.max_tokens,
                "return_full_text": False,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers)
                if resp.status_code != 200:
                    raise LLMProviderError(
                        f"HuggingFace API error {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                    )
                data = resp.json()

            if isinstance(data, list) and data:
                content = data[0].get("generated_text", "")
            elif isinstance(data, dict):
                content = data.get("generated_text", "")
            else:
                content = str(data)

            token_estimate = len(content.split())
            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider_name,
                completion_tokens=token_estimate,
                total_tokens=len(prompt.split()) + token_estimate,
                finish_reason="stop",
                request_id=request.request_id,
            )
        except httpx.TimeoutException as e:
            raise LLMProviderError(f"HuggingFace timeout: {e}")
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"HuggingFace error: {e}")

    async def stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        response = await self.complete(request)
        words = response.content.split()
        import asyncio
        for i, word in enumerate(words):
            await asyncio.sleep(0.03)
            is_last = i == len(words) - 1
            yield LLMStreamChunk(
                delta=word + ("" if is_last else " "),
                finish_reason="stop" if is_last else None,
                index=i,
                model=response.model,
            )

    async def health_check(self) -> bool:
        try:
            from ..base import LLMMessage
            req = LLMRequest(
                messages=[LLMMessage(role="user", content="hello")],
                max_tokens=10,
            )
            response = await self.complete(req)
            return True
        except Exception as e:
            logger.warning("HuggingFace health check failed: %s", e)
            return False
