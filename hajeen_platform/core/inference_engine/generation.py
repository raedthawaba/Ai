from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, List, Optional

from .inference_config import InferenceConfig

logger = logging.getLogger(__name__)


class TextGenerator:
    """Synchronous and asynchronous text generation over a loaded model."""

    def __init__(self, model: Any, tokenizer: Any, device: str = "cpu") -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.device = device

    def generate(self, prompt: str, config: InferenceConfig) -> str:
        try:
            import torch  # type: ignore

            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            input_ids = inputs["input_ids"]

            gen_kwargs = self._build_kwargs(config, input_ids)
            with torch.no_grad():
                output_ids = self.model.generate(input_ids, **gen_kwargs)

            new_ids = output_ids[0][input_ids.shape[-1]:]
            return self.tokenizer.decode(new_ids, skip_special_tokens=True)
        except ImportError as exc:
            raise RuntimeError("PyTorch not installed") from exc

    async def agenerate(self, prompt: str, config: InferenceConfig) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate, prompt, config)

    async def stream(
        self, prompt: str, config: InferenceConfig
    ) -> AsyncIterator[str]:
        try:
            from transformers import TextIteratorStreamer  # type: ignore
            import torch  # type: ignore
            from threading import Thread

            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            streamer = TextIteratorStreamer(
                self.tokenizer, skip_prompt=True, skip_special_tokens=True
            )
            gen_kwargs = self._build_kwargs(config, inputs["input_ids"])
            gen_kwargs["streamer"] = streamer

            thread = Thread(target=self.model.generate, kwargs={**inputs, **gen_kwargs})
            thread.start()

            for chunk in streamer:
                if chunk:
                    yield chunk
                await asyncio.sleep(0)
            thread.join()
        except ImportError as exc:
            raise RuntimeError("transformers / torch not installed") from exc

    def _build_kwargs(self, config: InferenceConfig, input_ids: Any) -> dict:
        import torch  # type: ignore

        kwargs: dict = {
            "max_new_tokens": config.max_new_tokens,
            "do_sample": config.do_sample,
            "repetition_penalty": config.repetition_penalty,
            "pad_token_id": getattr(self.tokenizer, "eos_token_id", 0),
        }
        if config.do_sample:
            if config.temperature > 0:
                kwargs["temperature"] = config.temperature
            if config.top_p < 1.0:
                kwargs["top_p"] = config.top_p
            if config.top_k > 0:
                kwargs["top_k"] = config.top_k
        if config.seed is not None:
            torch.manual_seed(config.seed)
        return kwargs
