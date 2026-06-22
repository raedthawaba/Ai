"""Phase 8.8 — Inference Tasks: مهام Celery للـ AI inference الثقيل."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from workers.celery_app import app as celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """تشغيل coroutine في Celery worker."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── 8.8.1 — Async Inference Task ──────────────────────────────────────────────

@celery_app.task(
    name="inference.async_infer",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    soft_time_limit=120,
    time_limit=180,
    queue="inference",
)
def async_infer_task(
    self,
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    session_id: Optional[str] = None,
    provider: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    مهمة Celery لـ LLM inference غير متزامن.

    مناسب للطلبات الثقيلة التي لا تحتاج نتيجة فورية.
    """
    task_id = self.request.id
    logger.info("Inference task started: %s", task_id)
    t_start = time.time()

    async def _run():
        from core.inference_engine.engine import get_inference_engine
        engine = get_inference_engine()
        if not engine._initialized:
            await engine.initialize()
        return await engine.infer(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            session_id=session_id,
            provider=provider,
        )

    try:
        result = _run_async(_run())
        elapsed = time.time() - t_start

        logger.info(
            "Inference task done: %s — tokens=%d latency=%.1fs",
            task_id, result.total_tokens, elapsed,
        )

        return {
            "task_id": task_id,
            "status": "completed",
            "response": result.cleaned_content,
            "model": result.model,
            "provider": result.provider,
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
            },
            "latency_ms": round(result.latency_ms, 2),
            "elapsed_s": round(elapsed, 2),
        }

    except Exception as exc:
        logger.error("Inference task failed %s: %s", task_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(exc),
            }


# ── 8.8.2 — Batch Inference Task ──────────────────────────────────────────────

@celery_app.task(
    name="inference.batch_infer",
    bind=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=720,
    queue="inference_batch",
)
def batch_infer_task(
    self,
    requests: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Dict[str, Any]:
    """
    مهمة Celery لـ Batch inference — معالجة عدة طلبات دفعة واحدة.
    """
    task_id = self.request.id
    logger.info("Batch inference started: %s (%d requests)", task_id, len(requests))
    t_start = time.time()

    async def _run_batch():
        from core.inference_engine.engine import get_inference_engine
        engine = get_inference_engine()
        if not engine._initialized:
            await engine.initialize()

        tasks = [
            engine.infer(
                messages=req.get("messages", []),
                model=req.get("model", model),
                temperature=req.get("temperature", temperature),
                max_tokens=req.get("max_tokens", max_tokens),
                session_id=req.get("session_id"),
            )
            for req in requests
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    try:
        results = _run_async(_run_batch())
        elapsed = time.time() - t_start

        processed_results = []
        success_count = 0
        error_count = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_count += 1
                processed_results.append({
                    "index": i,
                    "status": "error",
                    "error": str(result),
                })
            else:
                success_count += 1
                processed_results.append({
                    "index": i,
                    "status": "completed",
                    "response": result.cleaned_content,
                    "tokens": result.total_tokens,
                })

        logger.info(
            "Batch done: %s — success=%d errors=%d elapsed=%.1fs",
            task_id, success_count, error_count, elapsed,
        )

        return {
            "task_id": task_id,
            "status": "completed",
            "total": len(requests),
            "success": success_count,
            "errors": error_count,
            "results": processed_results,
            "elapsed_s": round(elapsed, 2),
        }

    except Exception as exc:
        logger.error("Batch inference failed %s: %s", task_id, exc)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(exc),
        }


# ── 8.8.3 — RAG Chat Task ─────────────────────────────────────────────────────

@celery_app.task(
    name="inference.rag_chat",
    bind=True,
    max_retries=2,
    soft_time_limit=180,
    queue="inference",
)
def rag_chat_task(
    self,
    message: str,
    session_id: Optional[str] = None,
    language: str = "ar",
    top_k: int = 5,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    مهمة RAG Chat كاملة للمعالجة في الخلفية.

    User Query → RAG Retrieval → Prompt → LLM → Response
    """
    task_id = self.request.id
    logger.info("RAG chat task started: %s query='%s'", task_id, message[:50])
    t_start = time.time()

    async def _run():
        from services.chat.chat_service import ChatRequest, get_chat_service
        service = get_chat_service()
        if not service._initialized:
            await service.initialize()

        return await service.chat(ChatRequest(
            message=message,
            session_id=session_id,
            language=language,
            use_rag=True,
            temperature=temperature,
            max_tokens=max_tokens,
            top_k=top_k,
        ))

    try:
        response = _run_async(_run())
        elapsed = time.time() - t_start

        return {
            "task_id": task_id,
            "status": "completed",
            "response": response.to_dict(),
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as exc:
        logger.error("RAG chat task failed %s: %s", task_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"task_id": task_id, "status": "failed", "error": str(exc)}


# ── 8.8.4 — Long-Running Analysis Task ────────────────────────────────────────

@celery_app.task(
    name="inference.analyze_document",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
    queue="inference_heavy",
)
def analyze_document_task(
    self,
    document_text: str,
    analysis_type: str = "summary",
    language: str = "ar",
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """
    تحليل مستند طويل باستخدام LLM.

    أنواع التحليل:
    - summary: تلخيص
    - extraction: استخراج معلومات
    - classification: تصنيف
    - qa: إجابة أسئلة
    """
    task_id = self.request.id
    logger.info(
        "Document analysis task: %s type=%s length=%d",
        task_id, analysis_type, len(document_text),
    )

    ANALYSIS_PROMPTS = {
        "summary": (
            "لخّص المستند التالي في 5-7 جمل مع أهم النقاط:\n\n{text}"
            if language == "ar"
            else "Summarize the following document in 5-7 sentences:\n\n{text}"
        ),
        "extraction": (
            "استخرج المعلومات الرئيسية من المستند التالي بتنسيق JSON:\n\n{text}"
            if language == "ar"
            else "Extract key information from the following document as JSON:\n\n{text}"
        ),
        "classification": (
            "صنّف المستند التالي وحدد موضوعه الرئيسي:\n\n{text}"
            if language == "ar"
            else "Classify the following document and identify its main topic:\n\n{text}"
        ),
    }

    prompt_template = ANALYSIS_PROMPTS.get(analysis_type, ANALYSIS_PROMPTS["summary"])
    # قص النص إذا كان طويلاً جداً
    max_doc_chars = 8000
    truncated = len(document_text) > max_doc_chars
    doc_text = document_text[:max_doc_chars] + ("..." if truncated else "")
    prompt = prompt_template.format(text=doc_text)

    async def _run():
        from core.inference_engine.engine import get_inference_engine
        engine = get_inference_engine()
        if not engine._initialized:
            await engine.initialize()
        return await engine.infer(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        )

    try:
        result = _run_async(_run())
        return {
            "task_id": task_id,
            "status": "completed",
            "analysis_type": analysis_type,
            "response": result.cleaned_content,
            "model": result.model,
            "tokens_used": result.total_tokens,
            "document_truncated": truncated,
        }
    except Exception as exc:
        logger.error("Document analysis failed %s: %s", task_id, exc)
        return {"task_id": task_id, "status": "failed", "error": str(exc)}
