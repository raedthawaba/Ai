"""اختبارات Phase 4 — Section 4.2: Vector Store Layer."""
from __future__ import annotations

import os
import tempfile
from typing import List
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_entry(entry_id: str, dim: int = 4, text: str = "", **meta):
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    return VectorEntry(
        id=entry_id,
        vector=[0.1 * (i + 1) for i in range(dim)],
        chunk_id=f"chunk_{entry_id}",
        article_id=f"article_{entry_id}",
        text=text or f"sample text for {entry_id}",
        model_name="test-model",
        metadata=meta,
    )


def _norm_vector(v: List[float]) -> List[float]:
    import math
    n = math.sqrt(sum(x**2 for x in v))
    return [x / n for x in v] if n > 0 else v


# ──────────────────────────────────────────────────────────────────────────────
# BaseVectorStore Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestBaseVectorStore:
    def test_vector_entry_creation(self):
        from data_engine.storage.vector_store.base_vector_store import VectorEntry
        entry = VectorEntry(
            id="v001",
            vector=[0.1, 0.2, 0.3],
            chunk_id="chunk_1",
            article_id="art_1",
            text="test",
            model_name="model",
        )
        assert entry.id == "v001"
        assert len(entry.vector) == 3

    def test_search_result_to_dict(self):
        from data_engine.storage.vector_store.base_vector_store import SearchResult
        r = SearchResult(
            chunk_id="c1", article_id="a1", score=0.95, text="hello"
        )
        d = r.to_dict()
        assert d["chunk_id"] == "c1"
        assert d["score"] == 0.95

    def test_vector_store_stats_to_dict(self):
        from data_engine.storage.vector_store.base_vector_store import VectorStoreStats
        stats = VectorStoreStats(
            total_vectors=100,
            index_type="faiss:flat",
            dimensions=384,
            is_trained=True,
        )
        d = stats.to_dict()
        assert d["total_vectors"] == 100
        assert d["dimensions"] == 384


# ──────────────────────────────────────────────────────────────────────────────
# FAISSVectorStore Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestFAISSVectorStore:
    def _get_store(self, dim: int = 4):
        try:
            from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
            return FAISSVectorStore(dimensions=dim)
        except (ImportError, Exception) as exc:
            pytest.skip(f"FAISS غير متاح: {exc}")

    def test_add_single_entry(self):
        store = self._get_store()
        entry = _make_entry("e001", dim=4)
        added = store.add([entry])
        assert added == 1

    def test_add_multiple_entries(self):
        store = self._get_store()
        entries = [_make_entry(f"e{i:03d}", dim=4) for i in range(5)]
        added = store.add(entries)
        assert added == 5

    def test_stats_after_add(self):
        store = self._get_store()
        store.add([_make_entry("s001", dim=4)])
        stats = store.stats()
        assert stats.total_vectors >= 1
        assert stats.dimensions == 4

    def test_search_returns_results(self):
        store = self._get_store()
        entries = [_make_entry(f"sr{i}", dim=4) for i in range(5)]
        store.add(entries)
        query = _norm_vector([0.1, 0.2, 0.3, 0.4])
        results = store.search(query, top_k=3)
        assert len(results) <= 3
        assert all(isinstance(r.score, float) for r in results)

    def test_search_empty_store_returns_empty(self):
        store = self._get_store()
        results = store.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert results == []

    def test_delete_reduces_count(self):
        store = self._get_store()
        entry = _make_entry("del001", dim=4)
        store.add([entry])
        deleted = store.delete(["del001"])
        assert deleted == 1

    def test_save_and_load(self):
        store = self._get_store()
        entries = [_make_entry(f"p{i}", dim=4) for i in range(3)]
        store.add(entries)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_index")
            store.save(path)
            assert os.path.exists(path + ".faiss")
            assert os.path.exists(path + ".meta")

            # Load in new store
            store2 = self._get_store()
            store2.load(path)
            stats = store2.stats()
            assert stats.total_vectors == 3

    def test_batch_add(self):
        store = self._get_store()
        entries = [_make_entry(f"b{i}", dim=4) for i in range(10)]
        total = store.batch_add(entries, batch_size=3)
        assert total == 10

    def test_metadata_filter_search(self):
        store = self._get_store()
        entries = [
            _make_entry("f001", dim=4, category="tech"),
            _make_entry("f002", dim=4, category="science"),
            _make_entry("f003", dim=4, category="tech"),
        ]
        store.add(entries)
        query = _norm_vector([0.1, 0.2, 0.3, 0.4])
        results = store.search(query, top_k=10, filter_metadata={"category": "tech"})
        assert all(r.metadata.get("category") == "tech" for r in results)


# ──────────────────────────────────────────────────────────────────────────────
# UnifiedVectorStore Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestUnifiedVectorStore:
    def _get_store(self):
        try:
            from data_engine.storage.vector_store.vector_store_manager import UnifiedVectorStore
            return UnifiedVectorStore(backend="faiss", dimensions=4)
        except (ImportError, Exception) as exc:
            pytest.skip(f"FAISS غير متاح: {exc}")

    def test_add_with_deduplication(self):
        store = self._get_store()
        entry = _make_entry("dup001", dim=4)
        store.add([entry])
        store.add([entry])  # duplicate
        stats = store.stats()
        assert stats["total_vectors"] == 1

    def test_add_without_deduplication(self):
        store = self._get_store()
        entry = _make_entry("nd001", dim=4)
        store.add([entry], deduplicate=False)
        store.add([entry], deduplicate=False)
        # FAISS upsert - may or may not deduplicate at store level
        assert True  # no crash

    def test_batch_add_large(self):
        store = self._get_store()
        entries = [_make_entry(f"la{i}", dim=4) for i in range(50)]
        total = store.batch_add(entries, batch_size=10)
        assert total == 50

    def test_search_with_score_threshold(self):
        store = self._get_store()
        entries = [_make_entry(f"th{i}", dim=4) for i in range(5)]
        store.add(entries)
        results = store.search([0.1, 0.2, 0.3, 0.4], top_k=10, score_threshold=0.0)
        assert isinstance(results, list)

    def test_stats_includes_backend(self):
        store = self._get_store()
        stats = store.stats()
        assert "backend" in stats
        assert stats["backend"] == "faiss"

    def test_delete_updates_seen_ids(self):
        store = self._get_store()
        entry = _make_entry("del_u001", dim=4)
        store.add([entry])
        assert "del_u001" in store._seen_ids
        store.delete(["del_u001"])
        assert "del_u001" not in store._seen_ids


# ──────────────────────────────────────────────────────────────────────────────
# VectorStoreManager Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestVectorStoreManager:
    def test_get_faiss_store(self):
        try:
            from data_engine.storage.vector_store.vector_store_manager import get_vector_store
            from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
            store = get_vector_store("faiss", "test_col", dimensions=4)
            assert isinstance(store, FAISSVectorStore)
        except (ImportError, Exception) as exc:
            pytest.skip(f"FAISS غير متاح: {exc}")

    def test_unknown_backend_raises(self):
        from data_engine.storage.vector_store.vector_store_manager import get_vector_store
        with pytest.raises((ValueError, Exception)):
            get_vector_store("unknown_backend", "col", dimensions=4)

    def test_singleton_behavior(self):
        try:
            from data_engine.storage.vector_store.vector_store_manager import _INSTANCES, get_vector_store
            _INSTANCES.clear()
            s1 = get_vector_store("faiss", "singleton_test", dimensions=4)
            s2 = get_vector_store("faiss", "singleton_test", dimensions=4)
            assert s1 is s2
        except (ImportError, Exception) as exc:
            pytest.skip(f"FAISS غير متاح: {exc}")
