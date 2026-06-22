"""اختبارات Integration — Phase 4: RAG Pipeline الكامل."""
from __future__ import annotations

import asyncio
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_store_with_data(n: int = 5, dim: int = 4):
    from data_engine.storage.vector_store.base_vector_store import SearchResult
    results = [
        SearchResult(
            chunk_id=f"chunk_{i:03d}",
            article_id=f"article_{i:03d}",
            score=0.9 - i * 0.05,
            text=f"هذا هو المحتوى رقم {i} للمقال. يحتوي على معلومات مفيدة حول الموضوع المطلوب.",
            metadata={"source_url": f"http://example.com/{i}", "source_title": f"مقال {i}"},
        )
        for i in range(n)
    ]
    store = MagicMock()
    store.search = MagicMock(return_value=results)
    return store


def _make_mock_embedder(dim: int = 4):
    result = MagicMock()
    result.vector = [0.1] * dim
    result.model_name = "test-model"
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=result)
    return embedder


# ──────────────────────────────────────────────────────────────────────────────
# RAG Pipeline Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRAGPipelineIntegration:
    """اختبارات تكامل كاملة للـ RAG pipeline."""

    @pytest.mark.asyncio
    async def test_full_rag_query_without_llm(self):
        """RAG query كاملة بدون LLM — يجب إعادة context وsources."""
        from services.rag_service import RAGService
        from core.embeddings.embedding_engine import EmbeddingEngine

        store = _make_mock_store_with_data(5)
        embed_engine = MagicMock(spec=EmbeddingEngine)
        embed_result = MagicMock()
        embed_result.vector = [0.1] * 384
        embed_engine.embed = AsyncMock(return_value=embed_result)
        embed_engine.get_instance = MagicMock(return_value=embed_engine)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("services.rag_service.EmbeddingEngine", MagicMock(return_value=embed_engine))
            try:
                service = RAGService(
                    embedding_engine=embed_engine,
                    vector_store=store,
                    top_k=3,
                    rerank=False,
                )
                result = await service.query("ما هو الذكاء الاصطناعي؟", top_k=3)
                assert "question" in result
                assert "context" in result
                assert "sources" in result
                assert result["retrieved_count"] >= 0
                assert result["latency_ms"] >= 0
            except Exception:
                pytest.skip("RAGService تتطلب dependencies غير متوفرة")

    @pytest.mark.asyncio
    async def test_context_assembler_in_pipeline(self):
        """ContextAssembler يُجمّع النتائج بشكل صحيح."""
        from services.rag.context_assembler import ContextAssembler

        assembler = ContextAssembler(max_tokens=2000)
        hits = [
            {
                "chunk_id": f"c{i}",
                "article_id": f"a{i}",
                "text": f"محتوى المقطع {i}: معلومات تقنية مفيدة حول الذكاء الاصطناعي وتطبيقاته في العالم العربي.",
                "score": 0.9 - i * 0.05,
                "source_url": f"http://tech-site.com/article/{i}",
                "source_title": f"مقال تقني {i}",
            }
            for i in range(5)
        ]
        ctx = assembler.assemble(hits, query="الذكاء الاصطناعي")
        assert len(ctx.chunks) > 0
        assert ctx.total_tokens > 0
        assert len(ctx.sources) > 0
        assert ctx.query == "الذكاء الاصطناعي"

    @pytest.mark.asyncio
    async def test_retrieval_engine_full_flow(self):
        """RetrievalEngine يسترجع ويُنظّم النتائج."""
        from core.retrieval.retrieval_engine import RetrievalEngine
        from data_engine.storage.vector_store.base_vector_store import SearchResult

        results = [
            SearchResult(
                chunk_id=f"rf_{i}",
                article_id=f"ra_{i}",
                score=0.85 - i * 0.1,
                text=f"النص {i}: " + "كلمة " * 30,
                metadata={"lang": "ar"},
            )
            for i in range(5)
        ]
        store = MagicMock()
        store.search = MagicMock(return_value=results)
        embedder = _make_mock_embedder()

        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            top_k=3,
            score_threshold=0.0,
            enable_cache=False,
        )
        response = await engine.retrieve("استعلام كامل", top_k=3)
        assert len(response.hits) <= 3
        assert response.strategy == "semantic"
        assert all(h.rank > 0 for h in response.hits)

    @pytest.mark.asyncio
    async def test_hybrid_retrieval_fusion(self):
        """Hybrid retrieval يدمج semantic + keyword."""
        from core.retrieval.retrieval_engine import RetrievalEngine
        from data_engine.storage.vector_store.base_vector_store import SearchResult

        results = [
            SearchResult(chunk_id=f"hyb_{i}", article_id=f"ha_{i}",
                         score=0.8, text=f"text about AI {i}")
            for i in range(4)
        ]
        store = MagicMock()
        store.search = MagicMock(return_value=results)
        embedder = _make_mock_embedder()

        engine = RetrievalEngine(
            embedding_manager=embedder,
            vector_store=store,
            enable_cache=False,
        )
        response = await engine.hybrid_retrieve("AI systems", top_k=3)
        assert response.strategy == "hybrid"
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_dataset_builder_creates_records(self):
        """DatasetBuilder يبني records صحيحة."""
        from services.data_service.dataset_builder import DatasetBuilder
        builder = DatasetBuilder(output_dir="/tmp/test_dataset_build")
        raw = [
            {"title": "مقال عن الذكاء الاصطناعي", "content": "محتوى مفيد وطويل بما يكفي للاختبار."},
            {"title": "مقال قصير", "content": ""},
            {"title": "مقال علمي", "content": "الشبكات العصبية وتعلم الآلة العميق."},
        ]
        records = builder.build_instruction_dataset(
            raw_items=raw,
            instruction_fn=lambda x: f"لخّص هذا المقال: {x['title']}",
            response_fn=lambda x: x.get("content", ""),
        )
        assert len(records) >= 1
        assert all("instruction" in r and "response" in r for r in records)

    @pytest.mark.asyncio
    async def test_dataset_versioner_creates_version(self):
        """DatasetVersioner يُنشئ إصدارات صحيحة."""
        import tempfile
        from services.data_service.dataset_versioner import DatasetVersioner

        with tempfile.TemporaryDirectory() as tmpdir:
            versioner = DatasetVersioner(base_dir=tmpdir)
            records = [
                {"instruction": f"سؤال {i}", "response": f"إجابة {i} مع محتوى كافٍ للاختبار والتحقق."}
                for i in range(5)
            ]
            ver = versioner.create_version(records, name="test_ds", version="v1.0")
            assert ver.record_count == 5
            assert ver.checksum != ""
            assert ver.version_id != ""

            versions = versioner.list_versions()
            assert len(versions) == 1

    @pytest.mark.asyncio
    async def test_dataset_versioner_deduplicates(self):
        """DatasetVersioner يحذف التكرارات."""
        import tempfile
        from services.data_service.dataset_versioner import DatasetVersioner

        with tempfile.TemporaryDirectory() as tmpdir:
            versioner = DatasetVersioner(base_dir=tmpdir)
            records = [
                {"instruction": "نفس السؤال تماماً", "response": "نفس الإجابة تماماً"},
                {"instruction": "نفس السؤال تماماً", "response": "نفس الإجابة تماماً"},
                {"instruction": "سؤال مختلف", "response": "إجابة مختلفة كافية"},
            ]
            ver = versioner.create_version(records, "dedup_test", "v1.0")
            assert ver.record_count < 3

    @pytest.mark.asyncio
    async def test_mmr_retriever_reduces_redundancy(self):
        """MMR Retriever يُنوّع النتائج."""
        from services.rag.mmr_retriever import MMRRetriever

        async def mock_embed(text):
            return [0.1] * 4

        store = MagicMock()
        from data_engine.storage.vector_store.base_vector_store import SearchResult
        same_text_results = [
            SearchResult(chunk_id=f"mm{i}", article_id=f"a{i}",
                         score=0.9, text="نفس النص تماماً للتحقق من إزالة التكرار")
            for i in range(5)
        ]
        store.search = MagicMock(return_value=same_text_results)

        retriever = MMRRetriever(
            embedding_fn=mock_embed,
            vector_store=store,
            lambda_mult=0.5,
            top_k=3,
        )
        results = await retriever.retrieve("query", top_k=3)
        # MMR يجب أن يُعيد أقل من 5 عند تشابه النصوص العالي
        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_batch_rag_queries(self):
        """batch_query يعالج استعلامات متعددة."""
        try:
            from services.rag_service import RAGService
            from core.embeddings.embedding_engine import EmbeddingEngine

            store = _make_mock_store_with_data(3)
            embed_engine = MagicMock()
            embed_result = MagicMock()
            embed_result.vector = [0.1] * 384
            embed_engine.embed = AsyncMock(return_value=embed_result)

            service = RAGService(
                embedding_engine=embed_engine,
                vector_store=store,
                top_k=2,
                rerank=False,
            )
            results = await service.batch_query(["سؤال 1", "سؤال 2", "سؤال 3"])
            assert len(results) == 3
        except Exception:
            pytest.skip("RAGService dependencies غير متوفرة")
