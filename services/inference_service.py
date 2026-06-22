from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from core.inference_engine import InferenceConfig
from core.llm.llm_manager import LLMManager

logger = logging.getLogger(__name__)


class InferenceService:
    """High-level service for synchronous and async text generation."""

    def __init__(self, llm_manager: Optional[LLMManager] = None) -> None:
        self._llm = llm_manager or LLMManager()
        logger.info("InferenceService initialized")

    async def generate(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        config: Optional[InferenceConfig] = None,
    ) -> Dict[str, Any]:
        cfg = config or InferenceConfig()
        start = time.perf_counter()
        try:
            text = await self._llm.agenerate(prompt, config=cfg, model_id=model_id)
            latency = time.perf_counter() - start
            return {
                "text": text,
                "model": model_id or self._llm.default_model,
                "latency_ms": round(latency * 1000, 2),
                "tokens_generated": max(1, len(text.split())),
                "finish_reason": "stop",
            }
        except Exception as exc:
            logger.error("Inference error: %s", exc)
            raise

    async def stream(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        config: Optional[InferenceConfig] = None,
    ) -> AsyncIterator[str]:
        cfg = config or InferenceConfig(stream=True)
        async for chunk in self._llm.astream(prompt, config=cfg, model_id=model_id):
            yield chunk

    async def batch_generate(
        self,
        prompts: List[str],
        model_id: Optional[str] = None,
        config: Optional[InferenceConfig] = None,
    ) -> List[Dict[str, Any]]:
        tasks = [self.generate(p, model_id, config) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                output.append({"error": str(r), "prompt_index": i})
            else:
                output.append(r)
        return output

    def health(self) -> Dict:
        return {"status": "ok", "llm_ready": self._llm.is_ready()}
