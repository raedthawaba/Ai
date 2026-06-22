"""
vLLM Server — integrates the vLLM high-performance inference engine
with PagedAttention for maximum GPU throughput.
"""
from __future__ import annotations

import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from vllm import AsyncLLMEngine, AsyncEngineArgs, SamplingParams
    from vllm.outputs import RequestOutput
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    logger.warning("vLLM not installed — vLLM server unavailable")


class VLLMServer:
    """High-performance inference server using vLLM with PagedAttention."""

    def __init__(
        self,
        model_name: str,
        tensor_parallel_size: int = 1,
        gpu_memory_utilization: float = 0.90,
        max_num_batched_tokens: int = 32768,
        max_num_seqs: int = 256,
        quantization: Optional[str] = None,
    ) -> None:
        if not VLLM_AVAILABLE:
            raise RuntimeError("vLLM is not installed. Run: pip install vllm")

        self.model_name = model_name
        self.engine: Optional[AsyncLLMEngine] = None
        self._engine_args = AsyncEngineArgs(
            model=model_name,
            tensor_parallel_size=tensor_parallel_size,
            gpu_memory_utilization=gpu_memory_utilization,
            max_num_batched_tokens=max_num_batched_tokens,
            max_num_seqs=max_num_seqs,
            quantization=quantization,
            trust_remote_code=True,
        )

    async def initialize(self) -> None:
        logger.info("Initializing vLLM engine for %s", self.model_name)
        self.engine = AsyncLLMEngine.from_engine_args(self._engine_args)
        logger.info("vLLM engine ready")

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        request_id: str = "req-0",
    ) -> str:
        if not self.engine:
            raise RuntimeError("vLLM engine not initialized")

        sampling_params = SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or [],
        )

        full_output = ""
        async for output in self.engine.generate(prompt, sampling_params, request_id):
            if output.finished:
                full_output = output.outputs[0].text
                break

        return full_output

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        request_id: str = "req-0",
    ) -> AsyncGenerator[str, None]:
        if not self.engine:
            raise RuntimeError("vLLM engine not initialized")

        sampling_params = SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or [],
        )

        previous_text = ""
        async for output in self.engine.generate(prompt, sampling_params, request_id):
            current_text = output.outputs[0].text
            delta = current_text[len(previous_text):]
            if delta:
                yield delta
            previous_text = current_text

    async def shutdown(self) -> None:
        if self.engine:
            await self.engine.shutdown_background_loop()
        logger.info("vLLM engine shut down")
