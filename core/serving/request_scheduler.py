"""
Request Scheduler — queues and prioritizes inference requests with
timeout handling, cancellation support, and backpressure.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

from core.serving.batching_engine import BatchingEngine, PendingRequest

logger = logging.getLogger(__name__)


class RequestPriority(IntEnum):
    HIGH = 0
    NORMAL = 1
    LOW = 2


@dataclass(order=True)
class ScheduledRequest:
    priority: RequestPriority
    enqueued_at: float = field(compare=False)
    request: PendingRequest = field(compare=False)


class RequestScheduler:
    """Schedules and dispatches inference requests with priority queuing."""

    def __init__(
        self,
        batching_engine: BatchingEngine,
        max_queue_size: int = 1000,
    ) -> None:
        self.batching_engine = batching_engine
        self.max_queue_size = max_queue_size
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._running = False
        self._submitted = 0
        self._completed = 0
        self._rejected = 0

    async def start(self) -> None:
        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatcher())
        logger.info("Request scheduler started (max_queue=%d)", self.max_queue_size)

    async def stop(self) -> None:
        self._running = False
        if self._dispatcher_task:
            self._dispatcher_task.cancel()

    async def submit(
        self,
        model: str,
        prompt: str,
        messages: Optional[List[Dict[str, str]]],
        generation_config: Dict[str, Any],
        request_id: Optional[str] = None,
        priority: RequestPriority = RequestPriority.NORMAL,
        timeout: float = 60.0,
    ) -> Any:
        if self._queue.full():
            self._rejected += 1
            raise RuntimeError("Inference queue full — try again later")

        request_id = request_id or str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        pending = PendingRequest(
            request_id=request_id,
            model=model,
            prompt=prompt,
            messages=messages,
            generation_config=generation_config,
            future=future,
        )

        scheduled = ScheduledRequest(
            priority=priority,
            enqueued_at=time.perf_counter(),
            request=pending,
        )

        await self._queue.put(scheduled)
        self._submitted += 1

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            if not future.done():
                future.cancel()
            raise RuntimeError(f"Request {request_id} timed out after {timeout}s")

    async def _dispatcher(self) -> None:
        while self._running:
            try:
                scheduled = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                asyncio.create_task(self._dispatch_request(scheduled))
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _dispatch_request(self, scheduled: ScheduledRequest) -> None:
        try:
            wait_ms = (time.perf_counter() - scheduled.enqueued_at) * 1000
            if wait_ms > 100:
                logger.warning(
                    "Request %s waited %.0fms in scheduler queue",
                    scheduled.request.request_id, wait_ms,
                )
            await self.batching_engine.submit(scheduled.request)
            self._completed += 1
        except Exception as exc:
            logger.exception("Dispatch failed: %s", exc)
            if not scheduled.request.future.done():
                scheduled.request.future.set_exception(exc)

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "queue_depth": self._queue.qsize(),
            "max_queue": self.max_queue_size,
            "submitted": self._submitted,
            "completed": self._completed,
            "rejected": self._rejected,
        }
