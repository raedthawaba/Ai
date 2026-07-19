"""Phase 8.3 — Inference Engine: المحرك الرئيسي للـ inference."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.llm.base import LLMMessage, LLMRequest, LLMResponse
from core.llm.llm_manager import LLMManager, get_llm_manager, get_llm_manager_sync
from .queue_manager import QueueManager
from .request_handler import InferenceJob, JobStatus, RequestHandler
from .response_handler import ProcessedResponse, ResponseHandler
from .stream_handler import StreamEvent, StreamHandler
from .token_tracker import TokenTracker

logger = logging.getLogger(__name__)

_engine_instance: Optional["InferenceEngine"] = None


class InferenceEngine:
    """
    المحرك الرئيسي لـ LLM Inference.

    يدير:
    - Sync & Async inference
    - Streaming responses
    - Request queue
    - Token tracking
    - Concurrency control
    - Cancellation support
    """

    def __init__(
        self,
        llm_manager: Optional[LLMManager] = None,
        max_concurrent: int = 5,
        queue_size: int = 100,
        default_timeout: float = 120.0,
    ):
        self._llm_manager = llm_manager
        self.request_handler = RequestHandler()
        self.response_handler = ResponseHandler()
        self.stream_handler = StreamHandler()
        self.token_tracker = TokenTracker()
        self.queue_manager = QueueManager(
            max_concurrent=max_concurrent,
            max_queue_size=queue_size,
            job_timeout=default_timeout,
        )
        self._initialized = False
        self._worker_task: Optional[asyncio.Task] = None

    @property
    def llm_manager(self) -> LLMManager:
        if self._llm_manager is None:
            self._llm_manager = get_llm_manager_sync()
        return self._llm_manager

    async def initialize(self) -> None:
        """تهيئة المحرك وبدء العمال."""
        if self._initialized:
            return

        await self.llm_manager.initialize()

        # بدء queue worker
        self._worker_task = asyncio.create_task(
            self.queue_manager.run_worker(self._execute_request)
        )

        self._initialized = True
        logger.info(
            "InferenceEngine initialized: provider=%s",
            self.llm_manager.settings.provider,
        )

    async def _execute_request(self, request: LLMRequest) -> LLMResponse:
        """تنفيذ طلب inference مباشرة."""
        return await self.llm_manager.complete(request)

    async def infer(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> ProcessedResponse:
        """
        Inference متزامن — ينتظر الاستجابة الكاملة.
        """
        if not self._initialized:
            await self.initialize()

        job = self.request_handler.create_job(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            session_id=session_id,
        )

        errors = self.request_handler.validate(job)
        if errors:
            raise ValueError(f"Invalid request: {', '.join(errors)}")

        t0 = time.perf_counter()
        response = await self.llm_manager.complete(
            job.request,
            provider_name=provider,
        )
        response.latency_ms = (time.perf_counter() - t0) * 1000

        self.token_tracker.record(
            request_id=job.job_id,
            model=response.model,
            provider=response.provider,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            session_id=session_id,
        )

        return self.response_handler.process(response)

    async def stream_infer(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        session_id: Optional[str] = None,
        stream_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Streaming inference — يُرجع events تدريجياً.
        """
        if not self._initialized:
            await self.initialize()

        job = self.request_handler.create_job(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            session_id=session_id,
        )

        sid = stream_id or job.job_id

        chunk_generator = self.llm_manager.stream(job.request)

        async for event in self.stream_handler.process_stream(chunk_generator, sid):
            yield event

    async def queue_infer(
        self,
        messages: List[Dict[str, str]],
        priority: int = 5,
        **kwargs,
    ) -> str:
        """
        إضافة طلب للطابور — يرجع job_id فوراً.
        """
        if not self._initialized:
            await self.initialize()

        job = self.request_handler.create_job(
            messages=messages,
            priority=priority,
            **kwargs,
        )

        job_id = await self.queue_manager.submit(job)
        logger.debug("Queued job: %s", job_id)
        return job_id

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """الحصول على حالة job في الطابور."""
        job = self.queue_manager.get_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "not_found"}
        return job.to_dict()

    def cancel_stream(self, stream_id: str) -> bool:
        """إلغاء streaming session."""
        return self.stream_handler.cancel_session(stream_id)

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات شاملة."""
        token_stats = self.token_tracker.get_stats()
        queue_stats = self.queue_manager.get_stats()
        return {
            "tokens": {
                "total_requests": token_stats.total_requests,
                "total_tokens": token_stats.total_tokens,
                "avg_per_request": round(token_stats.avg_tokens_per_request, 1),
                "avg_latency_ms": round(token_stats.avg_latency_ms, 2),
                "by_model": token_stats.by_model,
                "by_provider": token_stats.by_provider,
            },
            "queue": {
                "total_queued": queue_stats.total_queued,
                "completed": queue_stats.total_completed,
                "failed": queue_stats.total_failed,
                "current_size": queue_stats.current_queue_size,
                "active": queue_stats.active_jobs,
            },
        }

    async def shutdown(self) -> None:
        """إيقاف المحرك بأمان."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("InferenceEngine shut down")


def get_inference_engine() -> InferenceEngine:
    """Singleton instance للـ InferenceEngine."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = InferenceEngine()
    return _engine_instance
