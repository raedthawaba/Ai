from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.embeddings.embedding_engine import EmbeddingEngine
from services.rag.retriever import SemanticRetriever
from services.rag.reranker import CrossEncoderReranker
from services.rag.context_builder import ContextBuilder
from services.rag.citation_builder import CitationBuilder
from services.rag.hybrid_search import HybridSearcher

logger = logging.getLogger(__name__)


class RAGService:
    """Orchestrates the full RAG pipeline: retrieve → rerank → build → generate."""

    def __init__(
        self,
        embedding_engine: Optional[EmbeddingEngine] = None,
        vector_store: Optional[Any] = None,
        llm_manager: Optional[Any] = None,
        reranker_model: Optional[str] = None,
        top_k: int = 5,
        rerank: bool = True,
    ) -> None:
        self._embed = embedding_engine or EmbeddingEngine.get_instance()
        self._vector_store = vector_store
        self._llm = llm_manager
        self._retriever = SemanticRetriever(
            embedding_engine=self._embed,
            vector_store=vector_store,
            top_k=top_k * 2,
        )
        self._reranker = CrossEncoderReranker(model_name=reranker_model)
        self._context_builder = ContextBuilder()
        self._citation_builder = CitationBuilder()
        self._hybrid = HybridSearcher(self._retriever) if vector_store else None
        self.rerank = rerank
        logger.info("RAGService initialized")

    def set_vector_store(self, store: Any) -> None:
        self._vector_store = store
        self._retriever.set_vector_store(store)

    async def query(
        self,
        question: str,
        top_k: int = 5,
        rerank: Optional[bool] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        use_rerank = rerank if rerank is not None else self.rerank

        results = await self._retriever.aretrieve(question, top_k=top_k * 2)

        if use_rerank and results:
            results = self._reranker.rerank(question, results, top_k=top_k)
        else:
            results = results[:top_k]

        context = self._context_builder.build(results, query=question)
        sources = self._citation_builder.build_source_list(results)

        answer: Optional[str] = None
        if self._llm is not None:
            from core.inference_engine import InferenceConfig
            from core.prompts.prompt_builder import PromptBuilder
            builder = PromptBuilder(system_persona="rag_assistant")
            chunks = [r.content for r in results]
            prompt = builder.build_rag(question, chunks)
            answer = await self._llm.agenerate(prompt, config=InferenceConfig())

        latency = time.perf_counter() - start
        return {
            "question": question,
            "answer": answer,
            "context": context,
            "sources": sources,
            "retrieved_count": len(results),
            "latency_ms": round(latency * 1000, 2),
        }

    async def batch_query(
        self, questions: List[str], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        tasks = [self.query(q, top_k=top_k) for q in questions]
        return await asyncio.gather(*tasks, return_exceptions=False)
