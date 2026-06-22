"""9.11 — Embedding Engine Tests."""
from __future__ import annotations

import math
import pytest
from unittest.mock import MagicMock, patch

from core.embeddings.embedding_cache import EmbeddingCache
from core.embeddings.similarity import SimilarityScorer
from core.embeddings.batch_embedder import BatchEmbedder


class TestEmbeddingCache:
    def test_put_and_get(self):
        cache = EmbeddingCache(max_size=100)
        vec = [0.1, 0.2, 0.3]
        cache.put("hello world", vec)
        result = cache.get("hello world")
        assert result == vec

    def test_miss_returns_none(self):
        cache = EmbeddingCache()
        assert cache.get("non-existent text") is None

    def test_lru_eviction(self):
        cache = EmbeddingCache(max_size=3)
        for i in range(4):
            cache.put(f"text_{i}", [float(i)] * 3)
        assert len(cache._cache) <= 3

    def test_hit_rate_tracking(self):
        cache = EmbeddingCache()
        cache.put("test", [1.0, 2.0])
        cache.get("test")
        cache.get("test")
        cache.get("missing")
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_clear(self):
        cache = EmbeddingCache()
        cache.put("text", [1.0])
        cache.clear()
        assert cache.get("text") is None
        assert cache.stats()["size"] == 0


class TestSimilarityScorer:
    def test_cosine_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        score = SimilarityScorer.cosine(vec, vec)
        assert abs(score - 1.0) < 1e-6

    def test_cosine_orthogonal(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        score = SimilarityScorer.cosine(v1, v2)
        assert abs(score) < 1e-6

    def test_cosine_opposite(self):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        score = SimilarityScorer.cosine(v1, v2)
        assert score < 0

    def test_cosine_empty_vector(self):
        score = SimilarityScorer.cosine([], [])
        assert score == 0.0

    def test_normalize(self):
        vec = [3.0, 4.0]
        normalized = SimilarityScorer.normalize(vec)
        norm = math.sqrt(sum(x ** 2 for x in normalized))
        assert abs(norm - 1.0) < 1e-6

    def test_normalize_zero_vector(self):
        vec = [0.0, 0.0, 0.0]
        result = SimilarityScorer.normalize(vec)
        assert result == vec

    def test_rank_by_similarity(self):
        query = [1.0, 0.0, 0.0]
        candidates = [
            ("doc_a", [1.0, 0.0, 0.0]),
            ("doc_b", [0.0, 1.0, 0.0]),
            ("doc_c", [0.9, 0.1, 0.0]),
        ]
        ranked = SimilarityScorer.rank_by_similarity(query, candidates, top_k=2)
        assert len(ranked) == 2
        assert ranked[0][0] == "doc_a"

    def test_find_similar(self):
        query = [1.0, 0.0]
        corpus = [[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]]
        results = SimilarityScorer.find_similar(query, corpus, top_k=2)
        assert len(results) == 2
        assert results[0][0] == 0

    def test_dot_product(self):
        v1 = [1.0, 2.0, 3.0]
        v2 = [4.0, 5.0, 6.0]
        result = SimilarityScorer.dot_product(v1, v2)
        assert result == pytest.approx(32.0)


class TestBatchEmbedder:
    def test_embed_texts_calls_engine(self):
        mock_engine = MagicMock()
        mock_engine.embed_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]
        embedder = BatchEmbedder(mock_engine, batch_size=2)
        results = embedder.embed_texts(["text1", "text2"])
        assert len(results) == 2
        assert mock_engine.embed_batch.called

    def test_batch_splitting(self):
        calls = []
        mock_engine = MagicMock()
        mock_engine.embed_batch.side_effect = lambda texts: [[float(i)] * 3 for i in range(len(texts))]
        embedder = BatchEmbedder(mock_engine, batch_size=2)
        results = embedder.embed_texts(["a", "b", "c", "d", "e"])
        assert len(results) == 5

    def test_embed_documents(self):
        mock_engine = MagicMock()
        mock_engine.embed_batch.return_value = [[0.1, 0.2]]
        embedder = BatchEmbedder(mock_engine)
        docs = [{"id": "1", "content": "hello world"}]
        result = embedder.embed_documents(docs, text_field="content")
        assert len(result) == 1
        assert "embedding" in result[0]
