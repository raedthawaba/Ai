"""
Streaming Server — handles token-by-token streaming inference responses
using server-sent events for real-time output.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from .serving.model_pool import ModelPool

logger = logging.getLogger(__name__)


class StreamingServer:
    """Provides streaming inference via async generators."""

    def __init__(self, model_pool: ModelPool) -> None:
        self.model_pool = model_pool
        self._active_streams = 0

    async def stream(
        self,
        model: str,
        prompt: str,
        messages: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        stream_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        stream_id = stream_id or str(uuid.uuid4())
        self._active_streams += 1
        start = time.perf_counter()

        try:
            loaded_model = await self.model_pool.get(model)

            generation_config = {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "stop": stop or [],
                "stream": True,
            }

            token_queue: asyncio.Queue = asyncio.Queue()
            done_event = asyncio.Event()

            async def generate_tokens() -> None:
                try:
                    if hasattr(loaded_model, "stream_generate"):
                        async for token in loaded_model.stream_generate(
                            prompt, **generation_config
                        ):
                            await token_queue.put(token)
                    else:
                        result = await asyncio.to_thread(
                            loaded_model.generate, prompt, **generation_config
                        )
                        words = result.split()
                        for word in words:
                            await token_queue.put(word + " ")
                            await asyncio.sleep(0.01)
                except Exception as exc:
                    await token_queue.put({"error": str(exc)})
                finally:
                    done_event.set()

            asyncio.create_task(generate_tokens())

            token_count = 0
            while not (done_event.is_set() and token_queue.empty()):
                try:
                    token = await asyncio.wait_for(token_queue.get(), timeout=0.1)
                    if isinstance(token, dict) and "error" in token:
                        yield json.dumps({"error": token["error"]})
                        return

                    token_count += 1
                    chunk = {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [{
                            "delta": {"content": token},
                            "index": 0,
                            "finish_reason": None,
                        }],
                    }
                    yield json.dumps(chunk)

                except asyncio.TimeoutError:
                    continue

            latency_ms = (time.perf_counter() - start) * 1000
            final_chunk = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": len(prompt.split()),
                    "completion_tokens": token_count,
                    "latency_ms": round(latency_ms, 2),
                },
            }
            yield json.dumps(final_chunk)

        finally:
            self._active_streams -= 1

    @property
    def active_streams(self) -> int:
        return self._active_streams
