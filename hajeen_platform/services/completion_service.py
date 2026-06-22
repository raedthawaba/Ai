from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, Optional

from core.inference_engine import InferenceConfig
from core.llm.llm_manager import LLMManager

logger = logging.getLogger(__name__)


class CompletionService:
    """OpenAI-compatible text completion service."""

    def __init__(self, llm_manager: Optional[LLMManager] = None) -> None:
        self._llm = llm_manager or LLMManager()

    async def complete(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[list] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        config = InferenceConfig(
            max_new_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop_sequences=stop or [],
            stream=stream,
        )
        start = time.perf_counter()
        text = await self._llm.agenerate(prompt, config=config, model_id=model_id)
        latency = time.perf_counter() - start
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(text.split()))
        return {
            "id": f"cmpl-{int(time.time())}",
            "object": "text_completion",
            "model": model_id or self._llm.default_model,
            "choices": [
                {
                    "text": text,
                    "index": 0,
                    "finish_reason": "stop",
                    "logprobs": None,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "latency_ms": round(latency * 1000, 2),
        }

    async def stream_complete(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        config = InferenceConfig(
            max_new_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in self._llm.astream(prompt, config=config, model_id=model_id):
            yield chunk
