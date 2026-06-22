"""Phase 8.1 — LlamaCpp Provider: مزود llama.cpp للنماذج المحلية GGUF."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
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


class LlamaCppProvider(BaseLLMProvider):
    """
    مزود llama.cpp للتشغيل المحلي لنماذج GGUF.

    يتطلب:
        pip install llama-cpp-python

    النموذج: مسار ملف .gguf محلي
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._llm: Optional[object] = None
        self._model_path = config.model

    async def initialize(self) -> None:
        model_path = Path(self._model_path)
        if not model_path.exists():
            logger.warning(
                "LlamaCpp: model file not found at '%s'. "
                "Provider will fail unless model is loaded later.",
                self._model_path,
            )
            self._initialized = False
            return

        try:
            from llama_cpp import Llama
            self._llm = await asyncio.to_thread(
                Llama,
                model_path=str(model_path),
                n_ctx=4096,
                n_threads=4,
                verbose=False,
            )
            self._initialized = True
            logger.info("LlamaCpp initialized: %s", self._model_path)
        except ImportError:
            raise ImportError(
                "llama-cpp-python required: pip install llama-cpp-python"
            )
        except Exception as e:
            raise LLMProviderError(f"LlamaCpp init error: {e}")

    def _build_prompt(self, request: LLMRequest) -> str:
        """بناء prompt بتنسيق ChatML."""
        parts = ["<|im_start|>"]
        for msg in request.messages:
            parts.append(f"{msg.role}\n{msg.content}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n")
        return "".join(parts)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._initialized or not self._llm:
            raise LLMProviderError(
                f"LlamaCpp not initialized. Model file: {self._model_path}"
            )

        prompt = self._build_prompt(request)

        def _run() -> dict:
            return self._llm(
                prompt,
                max_tokens=request.max_tokens or self.config.max_tokens,
                temperature=request.temperature or self.config.temperature,
                top_p=self.config.top_p,
                stop=["<|im_end|>"],
                echo=False,
            )

        try:
            result = await asyncio.to_thread(_run)
            content = result["choices"][0]["text"].strip()
            usage = result.get("usage", {})

            return LLMResponse(
                content=content,
                model=self._model_path,
                provider=self.provider_name,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                finish_reason=result["choices"][0].get("finish_reason", "stop"),
                request_id=request.request_id,
            )
        except Exception as e:
            raise LLMProviderError(f"LlamaCpp inference error: {e}")

    async def stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        if not self._initialized or not self._llm:
            raise LLMProviderError("LlamaCpp not initialized")

        prompt = self._build_prompt(request)

        def _run_stream():
            return self._llm(
                prompt,
                max_tokens=request.max_tokens or self.config.max_tokens,
                temperature=request.temperature or self.config.temperature,
                stream=True,
                stop=["<|im_end|>"],
            )

        try:
            stream_iter = await asyncio.to_thread(_run_stream)
            index = 0
            for chunk in stream_iter:
                token = chunk["choices"][0]["text"]
                finish = chunk["choices"][0].get("finish_reason")
                if token:
                    yield LLMStreamChunk(
                        delta=token,
                        finish_reason=finish,
                        index=index,
                        model=self._model_path,
                    )
                    index += 1
        except Exception as e:
            raise LLMProviderError(f"LlamaCpp streaming error: {e}")

    async def health_check(self) -> bool:
        return self._initialized and self._llm is not None
