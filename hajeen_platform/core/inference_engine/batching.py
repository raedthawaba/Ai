from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class BatchRequest:
    request_id: str = field(default_factory=lambda: str(uuid4()))
    prompt: str = ""
    config: Optional[Any] = None
    future: Optional[asyncio.Future] = field(default=None, compare=False)
    enqueued_at: float = field(default_factory=time.time)


@dataclass
class BatchResult:
    request_id: str
    text: str
    tokens_generated: int
    processing_time: float
    error: Optional[str] = None


class BatchInferenceProcessor:
    """Collects individual requests and processes them together for throughput."""

    def __init__(
        self,
        max_batch_size: int = 8,
        max_wait_ms: float = 50.0,
    ) -> None:
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self._queue: asyncio.Queue[BatchRequest] = asyncio.Queue()
        self._running = False
        self._generator: Optional[Any] = None

    def set_generator(self, generator: Any) -> None:
        self._generator = generator

    async def submit(self, prompt: str, config: Any) -> str:
        loop = asyncio.get_event_loop()
        future: asyncio.Future[str] = loop.create_future()
        req = BatchRequest(prompt=prompt, config=config, future=future)
        await self._queue.put(req)
        return await future

    async def run(self) -> None:
        self._running = True
        logger.info("BatchInferenceProcessor started")
        while self._running:
            batch = await self._collect_batch()
            if batch:
                await self._process_batch(batch)

    async def _collect_batch(self) -> List[BatchRequest]:
        batch: List[BatchRequest] = []
        deadline = time.monotonic() + self.max_wait_ms / 1000.0
        while len(batch) < self.max_batch_size:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                req = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                batch.append(req)
            except asyncio.TimeoutError:
                break
        return batch

    async def _process_batch(self, batch: List[BatchRequest]) -> None:
        if self._generator is None:
            for req in batch:
                if req.future and not req.future.done():
                    req.future.set_exception(RuntimeError("No generator configured"))
            return

        tasks = [
            asyncio.create_task(
                self._run_single(req)
            )
            for req in batch
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_single(self, req: BatchRequest) -> None:
        try:
            result = await self._generator.agenerate(req.prompt, req.config)
            if req.future and not req.future.done():
                req.future.set_result(result)
        except Exception as exc:
            if req.future and not req.future.done():
                req.future.set_exception(exc)

    def stop(self) -> None:
        self._running = False
