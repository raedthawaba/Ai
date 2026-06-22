"""اختبارات Phase 4 — Section 4.1: Embedding Pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_embedding_manager(dim: int = 384) -> MagicMock:
    """يُنشئ EmbeddingManager مُحاكى."""
    manager = MagicMock()
    result = MagicMock()
    result.vector = [0.1] * dim
    result.model_name = "test-model"
    result.dimension = dim
    manager.embed = AsyncMock(return_value=result)
    manager.embed_batch = AsyncMock(return_value=[result])
    manager.dimensions = dim
    return manager


# ──────────────────────────────────────────────────────────────────────────────
# EmbeddingCache Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEmbeddingCache:
    def test_cache_miss_returns_none(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache(max_size=100)
        assert cache.get("hello", "model-a") is None

    def test_cache_put_and_get(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache(max_size=100)
        vec = [0.5, 0.3, 0.1]
        cache.put("hello", "model-a", vec)
        assert cache.get("hello", "model-a") == vec

    def test_cache_different_models_isolated(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache(max_size=100)
        cache.put("text", "model-a", [1.0])
        cache.put("text", "model-b", [2.0])
        assert cache.get("text", "model-a") == [1.0]
        assert cache.get("text", "model-b") == [2.0]

    def test_cache_eviction_on_max_size(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache(max_size=3)
        for i in range(5):
            cache.put(f"text_{i}", "model", [float(i)])
        assert len(cache._store) <= 3

    def test_hit_rate_zero_initially(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache()
        assert cache.hit_rate == 0.0

    def test_hit_rate_after_hits(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache()
        cache.put("text", "m", [1.0])
        cache.get("text", "m")   # hit
        cache.get("miss", "m")   # miss
        assert cache.hit_rate == 0.5

    def test_cache_stats(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingCache
        cache = EmbeddingCache(max_size=50)
        stats = cache.stats()
        assert "size" in stats
        assert "hits" in stats
        assert "hit_rate" in stats


# ──────────────────────────────────────────────────────────────────────────────
# EmbeddingPipeline Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEmbeddingPipeline:
    @pytest.mark.asyncio
    async def test_embed_single_job(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager(dim=384)
        pipeline = EmbeddingPipeline(manager, batch_size=8, cache_enabled=True)
        job = EmbeddingJob(text="مرحبا بالعالم", chunk_id="c001", article_id="a001")
        output = await pipeline.embed_job(job)
        assert output is not None
        assert output.chunk_id == "c001"
        assert len(output.vector) == 384
        assert output.cached is False

    @pytest.mark.asyncio
    async def test_embed_job_uses_cache(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager, cache_enabled=True)
        job = EmbeddingJob(text="cached text", chunk_id="c002", article_id="a001")

        out1 = await pipeline.embed_job(job)
        out2 = await pipeline.embed_job(job)  # should be cached

        assert out2 is not None
        assert out2.cached is True
        assert manager.embed.call_count == 1  # called only once

    @pytest.mark.asyncio
    async def test_embed_batch_empty_returns_empty(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager)
        outputs, errors = await pipeline.embed_batch([])
        assert outputs == []
        assert errors == 0

    @pytest.mark.asyncio
    async def test_embed_batch_multiple_jobs(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager(dim=384)
        pipeline = EmbeddingPipeline(manager, batch_size=4, cache_enabled=False)
        jobs = [
            EmbeddingJob(text=f"text_{i}", chunk_id=f"c{i:03d}", article_id="a001")
            for i in range(10)
        ]
        outputs, errors = await pipeline.embed_batch(jobs)
        assert len(outputs) == 10
        assert errors == 0

    @pytest.mark.asyncio
    async def test_embed_pipeline_handles_error_gracefully(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = MagicMock()
        manager.embed = AsyncMock(side_effect=Exception("model error"))
        pipeline = EmbeddingPipeline(manager, cache_enabled=False)
        job = EmbeddingJob(text="fail", chunk_id="c999", article_id="a001")
        output = await pipeline.embed_job(job)
        assert output is None

    @pytest.mark.asyncio
    async def test_embed_pipeline_truncates_long_text(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager, max_text_length=100)
        long_text = "word " * 500
        job = EmbeddingJob(text=long_text, chunk_id="c001", article_id="a001")
        await pipeline.embed_job(job)
        # التحقق أن النص مُقلَّص
        actual_text = manager.embed.call_args.kwargs.get("text") or manager.embed.call_args.args[0] if manager.embed.called else ""
        if actual_text:
            assert len(actual_text) <= 100

    def test_pipeline_metrics(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager)
        metrics = pipeline.metrics()
        assert "total_processed" in metrics
        assert "total_cached" in metrics
        assert "batch_size" in metrics


# ──────────────────────────────────────────────────────────────────────────────
# EmbeddingManager Tests (integration-style with mocked model)
# ──────────────────────────────────────────────────────────────────────────────

class TestEmbeddingManagerInterface:
    @pytest.mark.asyncio
    async def test_embed_returns_result(self):
        from core.embeddings.embedding_manager import EmbeddingManager
        from core.embeddings.base import EmbeddingResult

        manager = EmbeddingManager.__new__(EmbeddingManager)
        manager._default_model_name = "test"
        manager._lock = asyncio.Lock()
        manager._models = {}
        manager._default_config = MagicMock()

        mock_model = MagicMock()
        mock_result = EmbeddingResult(
            text="",
            vector=[0.1] * 384,
            model_name="test",
            dimensions=384,
            latency_ms=0.0,
            chunk_id="c1",
            article_id="a1",
        )
        mock_model.embed = AsyncMock(return_value=mock_result)
        mock_model.is_loaded = True
        manager._models["test"] = mock_model

        result = await manager.embed("hello", chunk_id="c1", article_id="a1", model_name="test")
        assert result is not None
        assert len(result.vector) == 384

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list(self):
        from core.embeddings.embedding_manager import EmbeddingManager
        from core.embeddings.base import EmbeddingResult

        manager = EmbeddingManager.__new__(EmbeddingManager)
        manager._default_model_name = "test"
        manager._lock = asyncio.Lock()
        manager._models = {}
        manager._default_config = MagicMock()

        mock_results = [
            EmbeddingResult(text="", vector=[0.1]*384, model_name="test", dimensions=384, latency_ms=0.0, chunk_id=f"c{i}", article_id="a1")
            for i in range(3)
        ]
        mock_model = MagicMock()
        mock_model.embed_batch = AsyncMock(return_value=mock_results)
        mock_model.is_loaded = True
        manager._models["test"] = mock_model

        results = await manager.embed_batch(["t1", "t2", "t3"], model_name="test")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_health_check_returns_dict(self):
        from core.embeddings.embedding_manager import EmbeddingManager

        manager = EmbeddingManager.__new__(EmbeddingManager)
        manager._default_model_name = "test"
        manager._lock = asyncio.Lock()
        manager._models = {}
        manager._default_config = MagicMock()

        mock_model = MagicMock()
        mock_model.health_check = AsyncMock(return_value=True)
        mock_model.dimensions = 384
        mock_model.is_loaded = True
        manager._models["test"] = mock_model

        health = await manager.health_check()
        assert "status" in health
        assert "dimensions" in health


# ──────────────────────────────────────────────────────────────────────────────
# Multilingual Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMultilingualEmbedding:
    @pytest.mark.asyncio
    async def test_arabic_text_embedding(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager)
        arabic_texts = [
            "الذكاء الاصطناعي وتعلم الآلة",
            "البحث الدلالي في النصوص العربية",
            "نموذج اللغة الكبير للغة العربية",
        ]
        jobs = [
            EmbeddingJob(text=t, chunk_id=f"ar_{i}", article_id="arabic")
            for i, t in enumerate(arabic_texts)
        ]
        outputs, errors = await pipeline.embed_batch(jobs)
        assert len(outputs) == 3
        assert errors == 0

    @pytest.mark.asyncio
    async def test_english_text_embedding(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager)
        jobs = [
            EmbeddingJob(text="Machine learning and AI systems", chunk_id="en_0", article_id="english"),
        ]
        outputs, errors = await pipeline.embed_batch(jobs)
        assert len(outputs) == 1

    @pytest.mark.asyncio
    async def test_mixed_language_batch(self):
        from data_engine.embeddings.embedding_pipeline import EmbeddingJob, EmbeddingPipeline

        manager = _make_mock_embedding_manager()
        pipeline = EmbeddingPipeline(manager)
        texts = ["Arabic نص عربي", "English text", "Mixed: عربي and English"]
        jobs = [EmbeddingJob(text=t, chunk_id=f"m_{i}", article_id="mixed") for i, t in enumerate(texts)]
        outputs, _ = await pipeline.embed_batch(jobs)
        assert len(outputs) == 3
