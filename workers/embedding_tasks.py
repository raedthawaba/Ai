"""Section 7.8 — Celery Background Embedding Tasks."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """تشغيل coroutine داخل Celery worker (sync context)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@celery_app.task(
    name="workers.embedding_tasks.generate_embeddings_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def generate_embeddings_task(
    self,
    texts: List[str],
    chunk_ids: Optional[List[str]] = None,
    article_id: Optional[str] = None,
    model_name: Optional[str] = None,
    store_vectors: bool = True,
) -> Dict[str, Any]:
    """
    توليد embeddings في الخلفية.

    Args:
        texts: قائمة النصوص
        chunk_ids: معرّفات الـ chunks (اختياري)
        article_id: معرّف المقال
        model_name: اسم النموذج
        store_vectors: هل يُخزَّن في Vector Store؟

    Returns:
        dict مع نتائج العملية
    """
    t0 = time.perf_counter()
    task_id = self.request.id

    try:
        logger.info(f"[{task_id}] بدء embedding task: {len(texts)} نص")

        async def _embed():
            from core.embeddings.embedding_manager import get_embedding_manager
            manager = get_embedding_manager()
            return await manager.embed_batch(
                texts,
                chunk_ids=chunk_ids,
                article_id=article_id,
                model_name=model_name,
            )

        results = _run_async(_embed())

        stored = 0
        if store_vectors and results:
            async def _store():
                from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
                from data_engine.storage.vector_store.base_vector_store import VectorEntry
                store = FAISSVectorStore(dimensions=results[0].dimensions)
                entries = [
                    VectorEntry(
                        id=r.chunk_id or f"emb_{i}",
                        vector=r.vector,
                        chunk_id=r.chunk_id or f"chunk_{i}",
                        article_id=r.article_id or article_id or "",
                        text=r.text,
                        model_name=r.model_name,
                    )
                    for i, r in enumerate(results)
                ]
                return store.add(entries)

            stored = _run_async(_store())

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[{task_id}] اكتمل: {len(results)} embeddings, {stored} مخزّن في {elapsed:.1f}ms"
        )
        return {
            "task_id": task_id,
            "status": "success",
            "total_embedded": len(results),
            "stored": stored,
            "elapsed_ms": round(elapsed, 2),
        }

    except Exception as exc:
        logger.error(f"[{task_id}] خطأ: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="workers.embedding_tasks.batch_embedding_task",
    bind=True,
    max_retries=2,
)
def batch_embedding_task(
    self,
    article_ids: List[str],
    batch_size: int = 32,
) -> Dict[str, Any]:
    """
    إعادة فهرسة مجموعة مقالات في الخلفية (batch mode).
    """
    t0 = time.perf_counter()
    processed = 0
    failed = 0

    for article_id in article_ids:
        try:
            generate_embeddings_task.delay(
                texts=[f"مقال: {article_id}"],
                article_id=article_id,
                store_vectors=False,
            )
            processed += 1
        except Exception as exc:
            logger.error(f"فشل جدولة {article_id}: {exc}")
            failed += 1

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "total": len(article_ids),
        "queued": processed,
        "failed": failed,
        "elapsed_ms": round(elapsed, 2),
    }


@celery_app.task(
    name="workers.embedding_tasks.reindex_embeddings_task",
    bind=True,
    max_retries=1,
)
def reindex_embeddings_task(self, force: bool = False) -> Dict[str, Any]:
    """
    إعادة بناء الـ index كاملاً من قاعدة البيانات.
    """
    t0 = time.perf_counter()
    logger.info("بدء reindex كامل...")

    async def _reindex():
        from data_engine.storage.vector_store.sqlite_vector_index import SQLiteVectorIndex
        store = SQLiteVectorIndex()
        stats = store.stats()
        return stats.total_vectors

    count = _run_async(_reindex())
    elapsed = (time.perf_counter() - t0) * 1000

    return {
        "status": "completed",
        "vectors_found": count,
        "elapsed_ms": round(elapsed, 2),
        "force": force,
    }
