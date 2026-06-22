"""
CPU Worker — handles CPU-intensive tasks: data processing, RAG retrieval,
document parsing, and background operations.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
CPU_COUNT = multiprocessing.cpu_count()


class CPUWorker:
    """Worker optimized for CPU-bound tasks with parallel execution."""

    def __init__(
        self,
        worker_id: str,
        max_workers: Optional[int] = None,
    ) -> None:
        self.worker_id = worker_id
        self.max_workers = max_workers or min(CPU_COUNT, 8)
        self.task_count = 0
        self.error_count = 0
        self._thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self._process_pool = ProcessPoolExecutor(
            max_workers=max(1, self.max_workers // 2)
        )

    def process_documents(
        self,
        documents: List[Dict[str, Any]],
        pipeline: str = "default",
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        results: List[Dict[str, Any]] = []
        errors: List[str] = []

        from data_engine.processing.document_processor import DocumentProcessor
        processor = DocumentProcessor(pipeline=pipeline)

        futures = {
            self._thread_pool.submit(processor.process, doc): doc
            for doc in documents
        }

        for future in as_completed(futures):
            try:
                result = future.result(timeout=60)
                results.append(result)
            except Exception as exc:
                errors.append(str(exc))
                self.error_count += 1
                logger.warning("Document processing failed: %s", exc)

        self.task_count += 1
        return {
            "status": "completed",
            "processed": len(results),
            "errors": len(errors),
            "results": results,
            "error_details": errors,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    def run_rag_retrieval(
        self,
        query: str,
        collection: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            from services.rag.retriever import RAGRetriever
            retriever = RAGRetriever(collection=collection)
            results = retriever.retrieve(query=query, top_k=top_k, filters=filters)
            self.task_count += 1

            return {
                "status": "success",
                "query": query,
                "results": results,
                "count": len(results),
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        except Exception as exc:
            self.error_count += 1
            logger.exception("RAG retrieval failed: %s", exc)
            raise

    def batch_parallel(
        self,
        func: Callable,
        items: List[Any],
        use_processes: bool = False,
    ) -> List[Any]:
        executor = self._process_pool if use_processes else self._thread_pool
        futures = {executor.submit(func, item): i for i, item in enumerate(items)}
        results = [None] * len(items)

        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result(timeout=300)
            except Exception as exc:
                logger.error("Batch item %d failed: %s", idx, exc)
                results[idx] = {"error": str(exc)}

        return results

    def health_check(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": "healthy",
            "cpu_count": CPU_COUNT,
            "max_workers": self.max_workers,
            "task_count": self.task_count,
            "error_count": self.error_count,
        }

    def shutdown(self) -> None:
        self._thread_pool.shutdown(wait=False)
        self._process_pool.shutdown(wait=False)
