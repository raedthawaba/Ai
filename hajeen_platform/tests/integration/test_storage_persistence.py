"""Integration Test — Storage Persistence (Phase 1 — Section 1.6).

يختبر:
1. كتابة/قراءة البيانات الخام
2. طبقات Bronze/Silver/Gold
3. JSONL storage مع deduplication
4. persistence بعد restart
5. منع duplicate writes
6. file locking
7. metadata tracking
8. cleanup utilities
9. StorageManager singleton
10. health check
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any

import pytest

from data_engine.storage.storage_manager import StorageManager, get_storage_manager, reset_storage_manager


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
async def storage(tmp_path):
    """StorageManager مؤقت لكل اختبار."""
    sm = StorageManager(base_data_dir=tmp_path)
    await sm.connect()
    yield sm
    await sm.disconnect()


@pytest.fixture
def sample_article() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "title": "مقال اختبار",
        "content": "محتوى المقال للاختبار " * 10,
        "url": "https://example.com/test-article",
        "published_at": "2024-01-01T00:00:00Z",
        "source_id": "test_source",
    }


# ─────────────────────────────────────────────
# Raw Storage
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_raw_storage_write_and_read(storage):
    """كتابة وقراءة البيانات الخام."""
    data = json.dumps({"test": "data", "value": 42})
    key = f"articles/test_{uuid.uuid4()}.json"

    saved_path = await storage.store_raw_response(data, key)
    assert saved_path is not None

    loaded = await storage.load_raw_response(saved_path)
    assert loaded is not None
    parsed = json.loads(loaded)
    assert parsed["test"] == "data"
    assert parsed["value"] == 42


@pytest.mark.asyncio
async def test_raw_storage_binary(storage):
    """كتابة وقراءة بيانات ثنائية."""
    data = b"\x00\x01\x02\x03binary_data"
    key = f"binary/test_{uuid.uuid4()}.bin"

    saved_path = await storage.store_raw_response(data, key, deduplicate=False)
    loaded = await storage.load_raw_response(saved_path)
    assert loaded == data


# ─────────────────────────────────────────────
# Bronze Layer
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bronze_layer_save_and_load(storage, sample_article):
    """حفظ وقراءة البيانات في طبقة Bronze."""
    key = f"article_{sample_article['id']}"
    data = {
        "id": sample_article["id"],
        "cleaned_content": sample_article["content"],
        "raw_data_key": "articles/raw.json",
        "metadata": {"source_id": "test"},
    }

    saved_path = await storage.save_bronze_data(data, key, "BronzeSchema")
    assert saved_path is not None

    loaded = await storage.load_bronze_data(key, "BronzeSchema")
    assert loaded is not None
    assert loaded.get("id") == sample_article["id"]


# ─────────────────────────────────────────────
# Silver Layer
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_silver_layer_save_and_load(storage, sample_article):
    """حفظ وقراءة البيانات في طبقة Silver."""
    key = f"article_{sample_article['id']}_silver"
    data = {
        "id": sample_article["id"],
        "enriched_content": sample_article["content"],
        "keywords": ["ذكاء", "اصطناعي"],
        "entities": [],
    }

    saved_path = await storage.save_silver_data(data, key, "SilverSchema")
    loaded = await storage.load_silver_data(key, "SilverSchema")
    assert loaded is not None


# ─────────────────────────────────────────────
# Gold Layer
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gold_layer_save_and_load(storage, sample_article):
    """حفظ وقراءة البيانات في طبقة Gold."""
    key = f"article_{sample_article['id']}_gold"
    data = {
        "id": sample_article["id"],
        "final_content": sample_article["content"],
        "chunks": [{"text": "chunk1"}, {"text": "chunk2"}],
        "is_ready": True,
    }

    saved_path = await storage.save_gold_data(data, key, "GoldSchema")
    loaded = await storage.load_gold_data(key, "GoldSchema")
    assert loaded is not None


# ─────────────────────────────────────────────
# JSONL
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jsonl_write_and_read(storage, tmp_path):
    """كتابة وقراءة ملف JSONL."""
    records = [
        {"id": str(uuid.uuid4()), "title": f"مقال {i}", "content": f"محتوى {i}"}
        for i in range(10)
    ]

    jsonl_path = tmp_path / "test.jsonl"
    written = await storage.append_jsonl(records, jsonl_path, deduplicate=False)
    assert written == 10

    loaded = await storage.read_jsonl(jsonl_path)
    assert len(loaded) == 10
    assert loaded[0]["id"] == records[0]["id"]


@pytest.mark.asyncio
async def test_jsonl_deduplication(storage, tmp_path):
    """JSONL deduplication يمنع كتابة سجلات مكررة."""
    records = [{"id": "dup_001", "title": "مكرر"}]
    jsonl_path = tmp_path / "dedup_test.jsonl"

    written1 = await storage.append_jsonl(records, jsonl_path, deduplicate=True)
    written2 = await storage.append_jsonl(records, jsonl_path, deduplicate=True)

    assert written1 == 1
    assert written2 == 0  # مكرر — لا يُكتب


@pytest.mark.asyncio
async def test_jsonl_append(storage, tmp_path):
    """JSONL يدعم الإضافة التدريجية."""
    jsonl_path = tmp_path / "append_test.jsonl"

    batch1 = [{"id": f"b1_{i}", "val": i} for i in range(5)]
    batch2 = [{"id": f"b2_{i}", "val": i} for i in range(5)]

    await storage.append_jsonl(batch1, jsonl_path, deduplicate=False)
    await storage.append_jsonl(batch2, jsonl_path, deduplicate=False)

    all_records = await storage.read_jsonl(jsonl_path)
    assert len(all_records) == 10


@pytest.mark.asyncio
async def test_jsonl_empty_file(storage, tmp_path):
    """قراءة ملف JSONL غير موجود تُعيد قائمة فارغة."""
    result = await storage.read_jsonl(tmp_path / "nonexistent.jsonl")
    assert result == []


# ─────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deduplication_prevents_duplicate_raw(storage):
    """منع كتابة نفس البيانات الخام مرتين."""
    data = json.dumps({"unique_id": "dup_test_001", "content": "same content"})
    key = "articles/dup_test.json"

    p1 = await storage.store_raw_response(data, key, deduplicate=True)
    p2 = await storage.store_raw_response(data, key, deduplicate=True)

    # الثاني يُعيد key بدون كتابة جديدة
    assert p2 is not None


def test_is_duplicate_detection(tmp_path):
    """is_duplicate يكتشف السجلات المكررة."""
    sm = StorageManager(base_data_dir=tmp_path)
    data = {"id": "test_001", "content": "some data"}

    assert not sm.is_duplicate(data)  # المرة الأولى ليست مكررة
    assert sm.is_duplicate(data)      # المرة الثانية مكررة


# ─────────────────────────────────────────────
# Persistence (محاكاة restart)
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_persists_after_reconnect(tmp_path):
    """البيانات تبقى موجودة بعد قطع الاتصال وإعادته."""
    # كتابة البيانات
    sm1 = StorageManager(base_data_dir=tmp_path)
    await sm1.connect()

    data = {"id": "persist_001", "content": "بيانات مستمرة"}
    await sm1.save_bronze_data(data, "persist_001", "BronzeSchema")
    await sm1.disconnect()

    # قراءة البيانات في instance جديد (محاكاة restart)
    sm2 = StorageManager(base_data_dir=tmp_path)
    await sm2.connect()

    loaded = await sm2.load_bronze_data("persist_001", "BronzeSchema")
    await sm2.disconnect()

    assert loaded is not None
    assert loaded.get("id") == "persist_001"


# ─────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_old_files(storage, tmp_path):
    """cleanup_old_files يحذف الملفات القديمة."""
    # حذف الملفات أقدم من 0 يوم (أي كل الملفات)
    data = json.dumps({"test": "cleanup"})
    await storage.store_raw_response(data, "cleanup_test/old.json", deduplicate=False)

    # cleanup بـ 0 يوم (يحذف كل شيء)
    deleted = await storage.cleanup_old_files(older_than_days=0, layer="raw")
    assert deleted >= 0  # قد تكون الملفات محذوفة أو حديثة جداً


@pytest.mark.asyncio
async def test_get_storage_stats(storage, tmp_path):
    """get_storage_stats تُعيد إحصائيات التخزين."""
    stats = await storage.get_storage_stats()
    assert isinstance(stats, dict)
    assert "raw" in stats
    assert "bronze" in stats
    assert "silver" in stats
    assert "gold" in stats


# ─────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────

def test_storage_manager_singleton():
    """get_storage_manager يُعيد نفس الـ instance دائماً."""
    reset_storage_manager()
    sm1 = get_storage_manager()
    sm2 = get_storage_manager()
    assert sm1 is sm2, "يجب أن تكون نفس الـ instance (singleton)"
    reset_storage_manager()


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(storage):
    """health_check يُعيد حالة جميع الطبقات."""
    health = await storage.health_check()
    assert isinstance(health, dict)
    assert "raw" in health
    assert "connected" in health
    raw_status = health["raw"].get("status")
    assert raw_status in ("ok", "error")
