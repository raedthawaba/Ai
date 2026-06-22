"""Phase 8.1 — Ollama Provider: مزود Ollama للنماذج المحلية."""
from __future__ import annotations

import json
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


class OllamaProvider(BaseLLMProvider):
    """
    مزود Ollama للنماذج المحلية (LLaMA, Mistral, Phi, إلخ).

    يتطلب تشغيل خادم Ollama محلياً:
        ollama serve
        ollama pull llama2

    API: http://localhost:11434
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._base_url = config.api_base or "http://localhost:11434"

    async def initialize(self) -> None:
        self._initialized = True
        logger.info(
            "Ollama provider initialized: base_url=%s model=%s",
            self._base_url, self.config.model,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._initialized:
            await self.initialize()

        model = request.model or self.config.model
        url = f"{self._base_url}/api/chat"

        payload = {
            "model": model,
            "messages": request.to_messages_list(),
            "stream": False,
            "options": {
                "temperature": request.temperature or self.config.temperature,
                "num_predict": request.max_tokens or self.config.max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise LLMProviderError(
                        f"Ollama error {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                    )
                data = resp.json()

            content = data.get("message", {}).get("content", "")
            usage = data.get("prompt_eval_count", 0)

            return LLMResponse(
                content=content,
                model=data.get("model", model),
                provider=self.provider_name,
                prompt_tokens=usage,
                completion_tokens=data.get("eval_count", 0),
                total_tokens=usage + data.get("eval_count", 0),
                finish_reason="stop",
                request_id=request.request_id,
            )
        except httpx.ConnectError:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Is 'ollama serve' running?"
            )
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"Ollama error: {e}")

    async def stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        if not self._initialized:
            await self.initialize()

        model = request.model or self.config.model
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": model,
            "messages": request.to_messages_list(),
            "stream": True,
            "options": {
                "temperature": request.temperature or self.config.temperature,
                "num_predict": request.max_tokens or self.config.max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    index = 0
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            delta = data.get("message", {}).get("content", "")
                            done = data.get("done", False)
                            if delta:
                                yield LLMStreamChunk(
                                    delta=delta,
                                    finish_reason="stop" if done else None,
                                    index=index,
                                    model=model,
                                )
                                index += 1
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self._base_url}"
            )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception as e:
            logger.debug("Ollama health check failed: %s", e)
            return False

    async def list_models(self) -> list:
        """قائمة النماذج المتاحة في Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
