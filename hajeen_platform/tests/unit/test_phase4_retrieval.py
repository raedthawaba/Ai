"""اختبارات Phase 4 — Section 4.3: Retrieval Engine."""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_search_result(chunk_id: str, score: float, text: str = "", **meta):
    from data_engine.storage.vector_store.base_vector_store import SearchResult
    return SearchResult(
        chunk_id=chunk_id,
        article_id=f"art_{chunk_id}",
        score=score,
        text=text or f"text for {chunk_id}",
        metadata=meta,
    )


def _make_mock_store(results=None):
    store = MagicMock()
    store.search = MagicMock(return_value=results or [])
    return store


def _make_mock_embedder(vector=None):
    dim = 384
    result = MagicMock()
    result.vector = vector or [0.1] * dim
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=result)
    return embedder


# ──────────────────────────────────────────────────────────────────────────────
# RetrievalEngine Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRetrievalEngine:
    def _get_engine(self, results=None, vector=None):
        from core.retrieval.retrieval_engine import RetrievalEngine
        store = _make_mock_store(results or [])
        embedder = _make_mock_embedder(vector)
        return RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            top_k=5,
            score_threshold=0.0,
            enable_cache=False,
        )

    @pytest.mark.asyncio
    async def test_retrieve_returns_response(self):
        results = [_make_search_result(f"c{i}", score=0.9 - i * 0.1) for i in range(3)]
        engine = self._get_engine(results)
        response = await engine.retrieve("test query")
        assert response.query == "test query"
        assert len(response.hits) <= 5
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_retrieve_empty_store_returns_empty(self):
        engine = self._get_engine([])
        response = await engine.retrieve("query")
        assert response.hits == []
        assert response.total == 0

    @pytest.mark.asyncio
    async def test_score_threshold_filters_low_scores(self):
        from core.retrieval.retrieval_engine import RetrievalEngine
        results = [
            _make_search_result("high", score=0.9),
            _make_search_result("low", score=0.05),
        ]
        store = _make_mock_store(results)
        embedder = _make_mock_embedder()
        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            score_threshold=0.1,
            enable_cache=False,
        )
        response = await engine.retrieve("query")
        assert all(h.score >= 0.1 for h in response.hits)

    @pytest.mark.asyncio
    async def test_duplicate_chunks_removed(self):
        from core.retrieval.retrieval_engine import RetrievalEngine
        results = [
            _make_search_result("dup_chunk", score=0.9),
            _make_search_result("dup_chunk", score=0.8),  # duplicate
            _make_search_result("unique_chunk", score=0.7),
        ]
        store = _make_mock_store(results)
        embedder = _make_mock_embedder()
        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            score_threshold=0.0,
            enable_cache=False,
        )
        response = await engine.retrieve("query", top_k=10)
        chunk_ids = [h.chunk_id for h in response.hits]
        assert len(chunk_ids) == len(set(chunk_ids))

    @pytest.mark.asyncio
    async def test_retrieve_assigns_ranks(self):
        results = [_make_search_result(f"c{i}", score=0.9 - i * 0.1) for i in range(3)]
        engine = self._get_engine(results)
        response = await engine.retrieve("query")
        for i, h in enumerate(response.hits):
            assert h.rank == i + 1

    @pytest.mark.asyncio
    async def test_retrieve_arabic_query(self):
        results = [_make_search_result("ar001", score=0.85, text="نص عربي")]
        engine = self._get_engine(results)
        response = await engine.retrieve("الذكاء الاصطناعي")
        assert response.query == "الذكاء الاصطناعي"

    @pytest.mark.asyncio
    async def test_multilingual_retrieve(self):
        results = [_make_search_result("ml001", score=0.80)]
        engine = self._get_engine(results)
        response = await engine.retrieve_multilingual("AI والذكاء الاصطناعي")
        assert response is not None

    @pytest.mark.asyncio
    async def test_hybrid_retrieve_strategy(self):
        results = [_make_search_result(f"h{i}", score=0.9 - i * 0.05) for i in range(5)]
        engine = self._get_engine(results)
        response = await engine.hybrid_retrieve("query", top_k=3)
        assert response.strategy == "hybrid"

    @pytest.mark.asyncio
    async def test_retrieval_timeout_returns_empty(self):
        from core.retrieval.retrieval_engine import RetrievalEngine

        async def slow_embed(*args, **kwargs):
            await asyncio.sleep(10)

        embedder = MagicMock()
        embedder.embed = slow_embed
        store = _make_mock_store()
        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            retrieval_timeout=0.01,
            enable_cache=False,
        )
        response = await engine.retrieve("timeout query")
        assert response.hits == []

    @pytest.mark.asyncio
    async def test_cache_returns_same_response(self):
        from core.retrieval.retrieval_engine import RetrievalEngine
        results = [_make_search_result("cached_c1", score=0.9)]
        store = _make_mock_store(results)
        embedder = _make_mock_embedder()
        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            enable_cache=True,
            cache_ttl=60,
        )
        r1 = await engine.retrieve("cached query")
        r2 = await engine.retrieve("cached query")
        assert r1.hits[0].chunk_id == r2.hits[0].chunk_id

    @pytest.mark.asyncio
    async def test_mmr_retrieval_reduces_redundancy(self):
        from core.retrieval.retrieval_engine import RetrievalEngine
        results = [_make_search_result(f"mmr{i}", score=0.9) for i in range(6)]
        store = _make_mock_store(results)
        embedder = _make_mock_embedder()
        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            use_mmr=True,
            mmr_lambda=0.5,
            enable_cache=False,
        )
        response = await engine.retrieve("diverse query", top_k=3)
        assert len(response.hits) <= 3


# ──────────────────────────────────────────────────────────────────────────────
# QueryNormalization Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestQueryNormalization:
    def test_normalize_trims_whitespace(self):
        from core.retrieval.retrieval_engine import _normalize_query
        assert _normalize_query("  hello  ") == "hello"

    def test_normalize_collapses_spaces(self):
        from core.retrieval.retrieval_engine import _normalize_query
        assert _normalize_query("a  b   c") == "a b c"

    def test_normalize_truncates_long_query(self):
        from core.retrieval.retrieval_engine import _normalize_query
        long = "w " * 2000
        result = _normalize_query(long)
        assert len(result) <= 1024


# ──────────────────────────────────────────────────────────────────────────────
# ContextAssembler Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestContextAssembler:
    def test_assemble_basic(self):
        from services.rag.context_assembler import ContextAssembler
        assembler = ContextAssembler(max_tokens=1000)
        hits = [
            {"chunk_id": "c1", "article_id": "a1", "text": "This is chunk one " * 10, "score": 0.9},
            {"chunk_id": "c2", "article_id": "a2", "text": "This is chunk two " * 10, "score": 0.8},
        ]
        ctx = assembler.assemble(hits, query="test")
        assert len(ctx.chunks) == 2
        assert ctx.total_tokens > 0

    def test_assemble_respects_token_budget(self):
        from services.rag.context_assembler import ContextAssembler
        assembler = ContextAssembler(max_tokens=100, reserve_tokens=10)
        hits = [
            {"chunk_id": f"c{i}", "article_id": f"a{i}",
             "text": "word " * 200, "score": 0.9}
            for i in range(5)
        ]
        ctx = assembler.assemble(hits, query="test")
        assert ctx.total_tokens <= 90  # 100 - 10 reserve

    def test_assemble_deduplicates(self):
        from services.rag.context_assembler import ContextAssembler
        assembler = ContextAssembler()
        same_text = "exact same content for deduplication test"
        hits = [
            {"chunk_id": f"dup{i}", "article_id": f"a{i}", "text": same_text, "score": 0.9}
            for i in range(3)
        ]
        ctx = assembler.assemble(hits, query="test")
        assert len(ctx.chunks) == 1

    def test_assemble_builds_sources(self):
        from services.rag.context_assembler import ContextAssembler
        assembler = ContextAssembler()
        hits = [
            {"chunk_id": "s1", "article_id": "art1", "text": "content one",
             "score": 0.9, "source_url": "http://example.com", "source_title": "Example"},
        ]
        ctx = assembler.assemble(hits, query="test")
        assert len(ctx.sources) == 1
        assert ctx.sources[0]["article_id"] == "art1"

    def test_prompt_block_format(self):
        from services.rag.context_assembler import ContextAssembler
        assembler = ContextAssembler()
        hits = [{"chunk_id": "p1", "article_id": "a1", "text": "hello world", "score": 0.9}]
        ctx = assembler.assemble(hits, query="test")
        block = ctx.to_prompt_block()
        assert "[CONTEXT]" in block
        assert "hello world" in block

    def test_empty_hits_returns_empty_context(self):
        from services.rag.context_assembler import ContextAssembler
        assembler = ContextAssembler()
        ctx = assembler.assemble([], query="test")
        assert ctx.chunks == []
        assert ctx.full_text == ""
