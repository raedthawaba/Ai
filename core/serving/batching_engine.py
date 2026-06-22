"""
Dynamic Batching Engine — groups inference requests into efficient batches
to maximize GPU utilization while minimizing latency.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    request_id: str
    model: str
    prompt: str
    messages: Optional[List[Dict[str, str]]]
    generation_config: Dict[str, Any]
    future: asyncio.Future
    enqueued_at: float = field(default_factory=time.perf_counter)


@dataclass
class Batch:
    batch_id: str
    model: str
    requests: List[PendingRequest]
    created_at: float = field(default_factory=time.perf_counter)

    @property
    def size(self) -> int:
        return len(self.requests)


class BatchingEngine:
    """Aggregates requests into batches for efficient GPU execution."""

    def __init__(
        self,
        max_batch_size: int,
        max_wait_ms: int,
        model_pool: Any,
    ) -> None:
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.model_pool = model_pool
        self._queues: Dict[str, asyncio.Queue] = {}
        self._processor_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._batch_count = 0
        self._total_requests = 0

    async def start(self) -> None:
        self._running = True
        logger.info(
            "Batching engine started (max_batch=%d, max_wait=%dms)",
            self.max_batch_size, self.max_wait_ms,
        )

    async def stop(self) -> None:
        self._running = False
        for task in self._processor_tasks.values():
            task.cancel()
        logger.info(
            "Batching engine stopped: %d batches, %d requests",
            self._batch_count, self._total_requests,
        )

    async def submit(self, request: PendingRequest) -> Any:
        model = request.model
        if model not in self._queues:
            self._queues[model] = asyncio.Queue(maxsize=1000)
            self._processor_tasks[model] = asyncio.create_task(
                self._batch_processor(model)
            )

        await self._queues[model].put(request)
        return await request.future

    async def _batch_processor(self, model: str) -> None:
        queue = self._queues[model]

        while self._running:
            batch_requests: List[PendingRequest] = []
            deadline = time.perf_counter() + (self.max_wait_ms / 1000.0)

            try:
                first = await asyncio.wait_for(
                    queue.get(), timeout=self.max_wait_ms / 1000.0
                )
                batch_requests.append(first)
            except asyncio.TimeoutError:
                continue

            while (
                len(batch_requests) < self.max_batch_size
                and time.perf_counter() < deadline
            ):
                try:
                    req = queue.get_nowait()
                    batch_requests.append(req)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.001)

            if batch_requests:
                await self._execute_batch(model, batch_requests)

    async def _execute_batch(
        self, model: str, requests: List[PendingRequest]
    ) -> None:
        batch_id = f"batch_{self._batch_count}"
        self._batch_count += 1
        self._total_requests += len(requests)
        start = time.perf_counter()

        logger.debug("Executing batch %s: %d requests for %s", batch_id, len(requests), model)

        try:
            loaded_model = await self.model_pool.get(model)
            prompts = [r.prompt for r in requests]
            configs = [r.generation_config for r in requests]

            results = await asyncio.to_thread(
                loaded_model.batch_generate, prompts, configs
            )

            latency_ms = (time.perf_counter() - start) * 1000
            for req, result in zip(requests, results):
                req.future.set_result({
                    "id": req.request_id,
                    "model": model,
                    "content": result,
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": len(req.prompt.split()), "completion_tokens": len(result.split())},
                    "latency_ms": round(latency_ms, 2),
                })

        except Exception as exc:
            logger.exception("Batch %s failed: %s", batch_id, exc)
            for req in requests:
                if not req.future.done():
                    req.future.set_exception(exc)

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "batch_count": self._batch_count,
            "total_requests": self._total_requests,
            "active_models": list(self._queues.keys()),
            "queue_depths": {m: q.qsize() for m, q in self._queues.items()},
        }
