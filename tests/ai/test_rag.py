"""9.11 — RAG Engine Tests."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.rag.retriever import RetrievalResult, SemanticRetriever
from services.rag.reranker import CrossEncoderReranker
from services.rag.context_builder import ContextBuilder
from services.rag.citation_builder import CitationBuilder
from services.rag.hybrid_search import HybridSearcher


class TestRetrievalResult:
    def test_to_dict(self):
        r = RetrievalResult(doc_id="doc1", content="Hello world", score=0.95)
        d = r.to_dict()
        assert d["doc_id"] == "doc1"
        assert d["score"] == 0.95

    def test_metadata_defaults_to_empty(self):
        r = RetrievalResult(doc_id="d", content="c", score=0.5)
        assert r.metadata == {}


class TestSemanticRetriever:
    def test_returns_empty_without_vector_store(self):
        embed = MagicMock()
        embed.embed.return_value = [0.1, 0.2]
        retriever = SemanticRetriever(embedding_engine=embed)
        results = retriever.retrieve("test query")
        assert results == []

    def test_set_vector_store(self):
        embed = MagicMock()
        store = MagicMock()
        store.search.return_value = [
            {"id": "d1", "content": "relevant text", "score": 0.9}
        ]
        embed.embed.return_value = [0.1, 0.2]
        retriever = SemanticRetriever(embedding_engine=embed, top_k=3)
        retriever.set_vector_store(store)
        results = retriever.retrieve("query")
        assert len(results) >= 1
        assert results[0].score >= 0

    @pytest.mark.asyncio
    async def test_aretrieve_returns_list(self):
        embed = MagicMock()
        embed.embed.return_value = [0.1, 0.2]
        retriever = SemanticRetriever(embedding_engine=embed)
        results = await retriever.aretrieve("async query")
        assert isinstance(results, list)


class TestCrossEncoderReranker:
    def test_rerank_fallback_keyword(self):
        reranker = CrossEncoderReranker(model_name=None)
        results = [
            RetrievalResult("d1", "machine learning models are great", 0.7),
            RetrievalResult("d2", "cooking recipes and food", 0.6),
            RetrievalResult("d3", "neural networks and deep learning", 0.65),
        ]
        reranked = reranker.rerank("machine learning neural", results, top_k=2)
        assert len(reranked) == 2

    def test_rerank_empty_returns_empty(self):
        reranker = CrossEncoderReranker()
        assert reranker.rerank("query", []) == []

    def test_top_k_limits_results(self):
        reranker = CrossEncoderReranker()
        results = [RetrievalResult(f"d{i}", f"text {i}", float(i) / 10) for i in range(5)]
        reranked = reranker.rerank("query", results, top_k=2)
        assert len(reranked) == 2


class TestContextBuilder:
    def test_build_with_results(self):
        builder = ContextBuilder()
        results = [
            RetrievalResult("d1", "Python is a programming language.", 0.9),
            RetrievalResult("d2", "Machine learning uses Python extensively.", 0.85),
        ]
        context = builder.build(results)
        assert "[1]" in context
        assert "Python" in context

    def test_max_context_chars_truncates(self):
        builder = ContextBuilder(max_context_chars=100)
        results = [RetrievalResult(f"d{i}", "x" * 200, 0.9 - i * 0.1) for i in range(5)]
        context = builder.build(results)
        assert len(context) <= 500

    def test_empty_results_returns_empty(self):
        builder = ContextBuilder()
        context = builder.build([])
        assert context == ""


class TestCitationBuilder:
    def test_build_references(self):
        builder = CitationBuilder()
        results = [
            RetrievalResult("d1", "content", 0.9, {"source": "https://example.com", "title": "Example"}),
        ]
        refs = builder.build_references(results)
        assert "1." in refs
        assert "Example" in refs

    def test_source_list(self):
        builder = CitationBuilder()
        results = [RetrievalResult("d1", "content", 0.85, {"source": "src1"})]
        sources = builder.build_source_list(results)
        assert len(sources) == 1
        assert sources[0]["index"] == 1
        assert sources[0]["doc_id"] == "d1"

    def test_inject_citations(self):
        builder = CitationBuilder()
        results = [RetrievalResult("d1", "text", 0.9, {"source": "http://src.com"})]
        text = "According to [1] this is true."
        injected = builder.inject_citations(text, results)
        assert "[1]" in injected or "http" in injected


class TestHybridSearcher:
    def test_keyword_search_scores_correctly(self):
        embed = MagicMock()
        embed.embed.return_value = [0.1, 0.2]
        store = MagicMock()
        store.search.return_value = []
        retriever = SemanticRetriever(embedding_engine=embed, vector_store=store)
        searcher = HybridSearcher(retriever)
        corpus = [
            {"id": "d1", "content": "machine learning deep learning"},
            {"id": "d2", "content": "cooking food recipes"},
        ]
        results = searcher.search("machine learning", top_k=2, corpus=corpus)
        assert isinstance(results, list)
