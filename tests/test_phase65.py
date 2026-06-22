"""Phase 6.5 — AI Data Layer Stabilization Tests.

يختبر:
  1. UnifiedArticle Schema — الحقول، التحويل، الهاشات
  2. ChunkingEngine — توليد chunks بكل الاستراتيجيات
  3. DeduplicationEngine — منع التكرار للمقالات والـ chunks
  4. Embedding Pipeline — interface + cache + storage + pipeline
  5. MetadataTracker — تسجيل ومتابعة البيانات الوصفية
  6. تكامل كامل: Article → Chunk → Dedup → Embed → Track
"""
from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path

# إضافة PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone
from typing import List


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(idx: int = 0, content: str = None) -> "Article":
    """إنشاء Article للاختبار."""
    from shared.schemas.article import Article, ArticleMetadata
    return Article(
        id=f"art_{idx:04d}",
        title=f"عنوان المقال رقم {idx}",
        content=content or (
            f"هذا هو محتوى المقال رقم {idx}. "
            "يحتوي على نص عربي وإنجليزي مختلط. "
            "This article discusses technology and artificial intelligence. "
            "تتحدث المقالة عن الذكاء الاصطناعي والتعلم الآلي. " * 5
        ),
        url=f"https://example.com/article/{idx}",
        published_at=datetime.now(tz=timezone.utc),
        metadata=ArticleMetadata(
            source_id=f"ch_{idx:04d}",
            language="ar",
            tags=["تقنية", "ذكاء اصطناعي"],
        ),
    )


def _make_unified(idx: int = 0, content: str = None) -> "UnifiedArticle":
    """إنشاء UnifiedArticle للاختبار."""
    from shared.schemas.unified_article import UnifiedArticle, SourceType
    return UnifiedArticle(
        id=f"art_unified_{idx:04d}",
        source=f"ch_{idx:04d}",
        source_type=SourceType.RSS,
        url=f"https://example.com/unified/{idx}",
        title=f"مقال موحّد رقم {idx}",
        raw_content=content or (
            f"محتوى خام للمقال رقم {idx}. "
            "هذا النص يحتوي على معلومات مفيدة حول الذكاء الاصطناعي. "
            "Artificial intelligence is transforming industries worldwide. "
            "تعمل تقنيات التعلم الآلي على تحسين الأنظمة الذكية. " * 4
        ),
        cleaned_content=content or (
            f"محتوى نظيف للمقال رقم {idx}. "
            "الذكاء الاصطناعي يُحدث ثورة في كل المجالات. " * 6
        ),
        language="ar",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — UnifiedArticle Schema
# ─────────────────────────────────────────────────────────────────────────────

def test_unified_article_fields():
    """التحقق من وجود جميع الحقول المطلوبة."""
    from shared.schemas.unified_article import UnifiedArticle
    art = _make_unified(1)

    required_fields = [
        "id", "source", "source_type", "url", "title",
        "raw_content", "cleaned_content", "summary",
        "language", "entities", "keywords", "categories",
        "chunk_ids", "embedding_id", "extra_metadata",
        "created_at", "updated_at",
    ]
    for field in required_fields:
        assert hasattr(art, field), f"حقل مفقود: {field}"

    print(f"  ✓ جميع الحقول الـ {len(required_fields)} موجودة")


def test_unified_article_from_legacy():
    """تحويل Article القديم إلى UnifiedArticle."""
    from shared.schemas.unified_article import UnifiedArticle
    old_art = _make_article(1)
    unified = UnifiedArticle.from_legacy_article(old_art)

    assert unified.id == old_art.id
    assert unified.title == old_art.title
    assert unified.raw_content == old_art.content
    assert unified.language == "ar"
    assert len(unified.tags) == 2
    print(f"  ✓ تحويل Article → UnifiedArticle: id={unified.id}")


def test_unified_article_hashes():
    """حساب الهاشات."""
    art = _make_unified(1)
    ch = art.compute_content_hash()
    uh = art.compute_url_hash()

    assert len(ch) == 64, f"content_hash طوله {len(ch)} بدلاً من 64"
    assert len(uh) == 64, f"url_hash طوله {len(uh)} بدلاً من 64"

    # نفس المقال = نفس الهاش
    art2 = _make_unified(1)
    assert art.compute_content_hash() == art2.compute_content_hash()
    print(f"  ✓ content_hash={ch[:16]}… url_hash={uh[:16]}…")


def test_unified_article_stage_progression():
    """تقدّم مراحل المعالجة."""
    from shared.schemas.unified_article import ArticleProcessingStage
    art = _make_unified(1)
    assert art.processing.processing_stage == ArticleProcessingStage.RAW

    art.advance_stage(ArticleProcessingStage.BRONZE)
    assert art.processing.processing_stage == ArticleProcessingStage.BRONZE
    assert "bronze" in art.processing.stage_timestamps

    art.mark_as_chunked(["chk_001", "chk_002"])
    assert art.chunk_count == 2

    art.mark_as_embedded("emb_001")
    assert art.embedding_id == "emb_001"
    assert art.processing.processing_stage == ArticleProcessingStage.EMBEDDED

    print("  ✓ تقدّم مراحل المعالجة: raw → bronze → embedded")


def test_unified_article_serialization():
    """التسلسل والاسترجاع."""
    art = _make_unified(1)
    d = art.to_dict()
    assert isinstance(d, dict)
    assert d["id"] == art.id
    assert "created_at" in d

    # إعادة إنشاء من dict
    from shared.schemas.unified_article import UnifiedArticle
    art2 = UnifiedArticle(**d)
    assert art2.id == art.id
    print(f"  ✓ تسلسل/استرجاع: {len(d)} حقل")


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Chunking Engine
# ─────────────────────────────────────────────────────────────────────────────

def test_chunking_recursive():
    """Recursive chunking — الأسلوب الافتراضي."""
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy
    )
    art = _make_unified(1)
    engine = ChunkingEngine(ChunkingConfig(
        strategy=ChunkingStrategy.RECURSIVE,
        chunk_size=200,
        overlap=30,
        min_chunk_chars=20,
    ))
    chunks = engine.chunk_article(art)

    assert len(chunks) > 0, "لا توجد chunks!"
    for ch in chunks:
        assert ch.chunk_id.startswith("chk_")
        assert ch.article_id == art.id
        assert ch.token_count > 0
        assert ch.char_count >= 20
        assert ch.strategy == "recursive"
        assert "article_id" in ch.metadata

    print(f"  ✓ Recursive chunking: {len(chunks)} chunks لمقال بـ {len(art.content_for_processing())} حرف")


def test_chunking_semantic():
    """Semantic chunking — تقسيم بناءً على الجمل."""
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy
    )
    art = _make_article(2)
    engine = ChunkingEngine(ChunkingConfig(
        strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=300,
        overlap=50,
        min_chunk_chars=30,
    ))

    from data_engine.processing.transformation.chunking_engine import DocumentChunk
    chunks = engine.chunk_text(art.content, article_id=art.id)
    assert len(chunks) > 0
    print(f"  ✓ Semantic chunking: {len(chunks)} chunks")


def test_chunking_fixed():
    """Fixed-size chunking."""
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy
    )
    text = "أ" * 1000  # 1000 حرف
    engine = ChunkingEngine(ChunkingConfig(
        strategy=ChunkingStrategy.FIXED,
        chunk_size=200,
        overlap=20,
        min_chunk_chars=10,
    ))
    chunks = engine.chunk_text(text, article_id="test_fixed")

    assert len(chunks) >= 4, f"عدد chunks غير كافٍ: {len(chunks)}"
    for ch in chunks:
        assert ch.char_count <= 200 + 5  # هامش صغير
    print(f"  ✓ Fixed chunking: 1000 حرف → {len(chunks)} chunks")


def test_chunking_token_aware():
    """Token-aware chunking."""
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy
    )
    text = "This is a test sentence. " * 50
    engine = ChunkingEngine(ChunkingConfig(
        strategy=ChunkingStrategy.TOKEN_AWARE,
        chunk_size=50,  # 50 tokens
        overlap=10,
        min_chunk_chars=20,
    ))
    chunks = engine.chunk_text(text, article_id="test_token")
    assert len(chunks) > 0
    print(f"  ✓ Token-aware chunking: {len(chunks)} chunks")


def test_chunk_document_fields():
    """التحقق من حقول DocumentChunk."""
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, DocumentChunk
    )
    engine = ChunkingEngine()
    chunks = engine.chunk_text("نص طويل " * 100, article_id="art_test")

    assert len(chunks) > 0
    chunk = chunks[0]
    assert isinstance(chunk, DocumentChunk)
    assert chunk.chunk_id  # غير فارغ
    assert chunk.article_id == "art_test"
    assert chunk.text
    assert chunk.token_count > 0
    assert chunk.char_count > 0
    assert isinstance(chunk.order, int)
    assert isinstance(chunk.metadata, dict)
    assert chunk.content_hash  # هاش تلقائي
    print(f"  ✓ DocumentChunk fields: id={chunk.chunk_id[:16]}… order={chunk.order}")


def test_chunk_deduplicator():
    """ChunkDeduplicator يمنع تكرار الـ chunks."""
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkDeduplicator
    )
    engine = ChunkingEngine()
    text = "محتوى للاختبار " * 50

    chunks1 = engine.chunk_text(text, article_id="art_001")
    chunks2 = engine.chunk_text(text, article_id="art_001")  # نفس النص!

    dedup = ChunkDeduplicator()
    unique1, dups1 = dedup.deduplicate(chunks1)
    unique2, dups2 = dedup.deduplicate(chunks2)  # كلها مكرّرة

    assert len(unique1) > 0
    assert len(unique2) == 0, f"يجب أن تكون 0 chunks فريدة في الجولة الثانية، وجدنا {len(unique2)}"
    assert len(dups2) == len(chunks2)
    print(f"  ✓ ChunkDeduplicator: جولة1={len(unique1)} فريدة، جولة2={len(dups2)} مكرّرة")


def test_chunking_batch():
    """chunk_batch لدُفعة من المقالات."""
    from data_engine.processing.transformation.chunking_engine import ChunkingEngine
    articles = [_make_unified(i) for i in range(5)]
    engine = ChunkingEngine()
    results = engine.chunk_batch(articles)

    assert len(results) == 5
    for art, chunks in results:
        assert len(chunks) > 0
    total = sum(len(c) for _, c in results)
    print(f"  ✓ chunk_batch: 5 مقالات → {total} chunks إجمالي")


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Deduplication Engine
# ─────────────────────────────────────────────────────────────────────────────

def test_dedup_url_detection():
    """كشف التكرار بالـ URL."""
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    engine = DeduplicationEngine(DeduplicationConfig(
        persistent=False,
        deduplicate_similar=False,
    ))
    articles = [_make_article(1), _make_article(1)]  # نفس الـ URL

    result = engine.deduplicate_articles(articles)
    assert result.unique_count == 1
    assert result.duplicate_count == 1
    assert "art_0001" in result.rejection_reasons
    print(f"  ✓ URL dedup: 2 مقالات متشابهة → 1 فريدة + 1 مكرّرة")


def test_dedup_content_detection():
    """كشف التكرار بالمحتوى."""
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    from shared.schemas.article import Article, ArticleMetadata

    engine = DeduplicationEngine(DeduplicationConfig(
        persistent=False,
        deduplicate_urls=False,
        deduplicate_similar=False,
    ))

    art1 = Article(
        id="art_dup_1",
        title="عنوان المقال",
        content="محتوى المقال الكامل هنا." * 20,
        url="https://example.com/1",
        published_at=datetime.now(tz=timezone.utc),
        metadata=ArticleMetadata(source_id="src_1"),
    )
    art2 = Article(
        id="art_dup_2",
        title="عنوان المقال",  # نفس العنوان
        content="محتوى المقال الكامل هنا." * 20,  # نفس المحتوى
        url="https://example.com/2",  # URL مختلف
        published_at=datetime.now(tz=timezone.utc),
        metadata=ArticleMetadata(source_id="src_2"),
    )

    result = engine.deduplicate_articles([art1, art2])
    assert result.unique_count == 1
    assert result.duplicate_count == 1
    print(f"  ✓ Content dedup: 2 مقالات متطابقة → 1 فريدة")


def test_dedup_unique_articles():
    """المقالات المختلفة تمرّ دون تكرار."""
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    engine = DeduplicationEngine(DeduplicationConfig(
        persistent=False, deduplicate_similar=False
    ))
    articles = [_make_article(i) for i in range(5)]

    result = engine.deduplicate_articles(articles)
    assert result.unique_count == 5
    assert result.duplicate_count == 0
    print(f"  ✓ 5 مقالات مختلفة → 5 فريدة، 0 مكرّرة")


def test_dedup_unified_articles():
    """إزالة تكرار UnifiedArticle."""
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    engine = DeduplicationEngine(DeduplicationConfig(
        persistent=False, deduplicate_similar=False
    ))
    arts = [_make_unified(1), _make_unified(1), _make_unified(2)]

    result = engine.deduplicate_articles(arts)
    assert result.unique_count == 2
    assert result.duplicate_count == 1
    print(f"  ✓ UnifiedArticle dedup: 3 مقالات (مكرّرة) → 2 فريدة")


def test_dedup_chunks():
    """إزالة تكرار الـ chunks."""
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    from data_engine.processing.transformation.chunking_engine import ChunkingEngine

    engine_dedup = DeduplicationEngine(DeduplicationConfig(persistent=False))
    engine_chunk = ChunkingEngine()

    art = _make_unified(1)
    chunks = engine_chunk.chunk_article(art) * 2  # تكرار عمدي

    result = engine_dedup.deduplicate_chunks(chunks)
    assert result.unique_count * 2 == len(chunks), (
        f"عدد الفريدة {result.unique_count} × 2 يجب = {len(chunks)}"
    )
    assert result.duplicate_count == result.unique_count
    print(f"  ✓ Chunk dedup: {len(chunks)} chunks → {result.unique_count} فريدة")


def test_dedup_stats():
    """إحصائيات DeduplicationEngine."""
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    engine = DeduplicationEngine(DeduplicationConfig(persistent=False))
    arts = [_make_article(i) for i in range(3)]
    engine.deduplicate_articles(arts)

    stats = engine.stats()
    assert "memory" in stats
    assert stats["memory"]["url_hashes"] >= 3
    print(f"  ✓ Stats: {stats['memory']}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Embedding Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_mock_embedder_single():
    """MockEmbedder لنص واحد."""
    from data_engine.ai.embeddings.base_embedder import MockEmbedder, EmbeddingRequest, EmbeddingConfig

    embedder = MockEmbedder(EmbeddingConfig(dimensions=128))
    req = EmbeddingRequest(
        request_id="req_001",
        text="هذا نص اختباري للـ embedding.",
        source_id="chunk_001",
        source_type="chunk",
    )
    result = asyncio.run(embedder.embed_one(req))

    assert result.is_valid
    assert len(result.vector) == 128
    assert result.embedding_id.startswith("emb_")
    assert result.provider == "mock"
    assert result.token_count > 0

    # نفس النص = نفس الـ vector
    result2 = asyncio.run(embedder.embed_one(req))
    assert result.vector == result2.vector, "المحدد يجب أن يكون ثابتاً"

    print(f"  ✓ MockEmbedder: dims={len(result.vector)} id={result.embedding_id}")


def test_mock_embedder_batch():
    """MockEmbedder لدُفعة من الطلبات."""
    from data_engine.ai.embeddings.base_embedder import MockEmbedder, EmbeddingRequest

    embedder = MockEmbedder()
    requests = [
        EmbeddingRequest(
            request_id=f"req_{i:03d}",
            text=f"نص الـ chunk رقم {i} للاختبار الشامل.",
            source_id=f"chunk_{i:03d}",
            source_type="chunk",
        )
        for i in range(10)
    ]
    results = asyncio.run(embedder.embed_batch(requests))

    assert len(results) == 10
    assert all(r.is_valid for r in results)
    # كل نص مختلف = vector مختلف
    vectors = [r.vector for r in results]
    assert len(set(str(v[:5]) for v in vectors)) > 1
    print(f"  ✓ embed_batch: 10 requests → 10 results صحيحة")


def test_embedding_cache():
    """EmbeddingCache — memory + hit/miss."""
    from data_engine.ai.embeddings.embedding_cache import EmbeddingCache

    cache = EmbeddingCache(memory_max_size=100, persistent=False)

    text = "نص للـ cache"
    model = "mock-v1"
    vector = [0.1, 0.2, 0.3, 0.4]

    # قبل التخزين
    assert cache.get(text, model) is None

    # بعد التخزين
    cache.set(text, model, vector, source_id="chunk_001")
    result = cache.get(text, model)
    assert result == vector

    # نص مختلف لا يُسترجع
    assert cache.get("نص مختلف", model) is None

    stats = cache.stats()
    assert stats["memory"]["hit_rate"] > 0

    print(f"  ✓ EmbeddingCache: hit_rate={stats['memory']['hit_rate']:.1%}")


def test_embedding_storage():
    """EmbeddingStorage — حفظ واسترجاع."""
    import tempfile
    from data_engine.ai.embeddings.embedding_storage import EmbeddingStorage, EmbeddingRecord

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        storage = EmbeddingStorage(db_path)
        record = EmbeddingRecord(
            embedding_id="emb_test_001",
            source_id="chunk_001",
            source_type="chunk",
            article_id="art_001",
            chunk_order=0,
            model_name="mock-v1",
            provider="mock",
            dimensions=384,
            vector=[0.1] * 384,
            token_count=25,
            text_preview="نص الاختبار",
            language="ar",
        )
        storage.save(record)

        # استرجاع بالمعرّف
        retrieved = storage.get("emb_test_001")
        assert retrieved is not None
        assert retrieved.embedding_id == "emb_test_001"
        assert len(retrieved.vector) == 384
        assert retrieved.article_id == "art_001"

        # استرجاع بالمقال
        recs = storage.get_by_article("art_001")
        assert len(recs) == 1

        stats = storage.stats()
        assert stats["total_embeddings"] == 1

        print(f"  ✓ EmbeddingStorage: حُفظ واسترجع embedding_id={retrieved.embedding_id}")
    finally:
        db_path.unlink(missing_ok=True)


def test_embedding_pipeline_chunks():
    """EmbeddingPipeline لدُفعة chunks كاملة."""
    import tempfile
    from data_engine.ai.embeddings.base_embedder import MockEmbedder, EmbeddingConfig
    from data_engine.ai.embeddings.embedding_cache import EmbeddingCache
    from data_engine.ai.embeddings.embedding_storage import EmbeddingStorage
    from data_engine.ai.embeddings.embedding_metadata import EmbeddingMetadataTracker
    from data_engine.ai.embeddings.embedding_pipeline import EmbeddingPipeline
    from data_engine.processing.transformation.chunking_engine import ChunkingEngine

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        embedder = MockEmbedder(EmbeddingConfig(dimensions=64, provider="mock"))
        cache = EmbeddingCache(persistent=False)
        storage = EmbeddingStorage(tmp / "emb.db")
        tracker = EmbeddingMetadataTracker(tmp / "meta.db")
        pipeline = EmbeddingPipeline(embedder, cache, storage, tracker)

        # إنشاء chunks
        art = _make_unified(1)
        engine = ChunkingEngine()
        chunks = engine.chunk_article(art)
        assert len(chunks) > 0, "لا توجد chunks!"

        # تشغيل الـ pipeline
        result = asyncio.run(pipeline.process_chunks(
            chunks, article_id=art.id, language="ar"
        ))

        assert result.total_requested == len(chunks)
        assert result.total_stored > 0
        assert result.total_errors == 0
        assert len(result.embedding_ids) > 0
        assert result.duration_ms > 0

        # التحقق من التخزين
        stored = storage.get_by_article(art.id)
        assert len(stored) > 0

        print(
            f"  ✓ EmbeddingPipeline: {len(chunks)} chunks → "
            f"{result.total_stored} embeddings مُخزّنة "
            f"في {result.duration_ms:.1f}ms"
        )


def test_embedding_pipeline_article():
    """EmbeddingPipeline لمقال كامل (chunking + embedding)."""
    import tempfile
    from data_engine.ai.embeddings.base_embedder import MockEmbedder, EmbeddingConfig
    from data_engine.ai.embeddings.embedding_cache import EmbeddingCache
    from data_engine.ai.embeddings.embedding_storage import EmbeddingStorage
    from data_engine.ai.embeddings.embedding_metadata import EmbeddingMetadataTracker
    from data_engine.ai.embeddings.embedding_pipeline import EmbeddingPipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pipeline = EmbeddingPipeline(
            embedder=MockEmbedder(EmbeddingConfig(dimensions=64)),
            cache=EmbeddingCache(persistent=False),
            storage=EmbeddingStorage(tmp / "emb.db"),
            tracker=EmbeddingMetadataTracker(tmp / "meta.db"),
        )

        art = _make_article(5)
        result = asyncio.run(pipeline.process_article(art))

        assert result.total_stored > 0
        assert result.total_errors == 0

        print(
            f"  ✓ process_article: مقال كامل → "
            f"{result.total_stored} embeddings"
        )


def test_embedding_cache_hit():
    """Cache hit يقلّل الطلبات للـ API."""
    import tempfile
    from data_engine.ai.embeddings.base_embedder import MockEmbedder, EmbeddingConfig
    from data_engine.ai.embeddings.embedding_cache import EmbeddingCache
    from data_engine.ai.embeddings.embedding_storage import EmbeddingStorage
    from data_engine.ai.embeddings.embedding_metadata import EmbeddingMetadataTracker
    from data_engine.ai.embeddings.embedding_pipeline import EmbeddingPipeline
    from data_engine.processing.transformation.chunking_engine import ChunkingEngine

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        shared_cache = EmbeddingCache(persistent=False)
        pipeline = EmbeddingPipeline(
            embedder=MockEmbedder(EmbeddingConfig(dimensions=64)),
            cache=shared_cache,
            storage=EmbeddingStorage(tmp / "emb.db"),
            tracker=EmbeddingMetadataTracker(tmp / "meta.db"),
        )

        art = _make_unified(1)
        engine = ChunkingEngine()
        chunks = engine.chunk_article(art)

        # تشغيل أول مرة
        result1 = asyncio.run(pipeline.process_chunks(chunks, article_id=art.id))
        # تشغيل ثاني — يجب أن يُستخدم الـ cache
        result2 = asyncio.run(pipeline.process_chunks(chunks, article_id=art.id))

        assert result2.total_cached > 0, "الجولة الثانية يجب أن تُستخدم الـ cache"

        print(
            f"  ✓ Cache hit: جولة1 computed={result1.total_computed}, "
            f"جولة2 cached={result2.total_cached}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Metadata Layer
# ─────────────────────────────────────────────────────────────────────────────

def test_metadata_tracker_article():
    """تسجيل بيانات المقال في MetadataTracker."""
    import tempfile
    from data_engine.metadata.tracker import MetadataTracker, ArticleMetadataRecord

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        tracker = MetadataTracker(db_path)
        record = ArticleMetadataRecord(
            article_id="art_meta_001",
            source_id="ch_001",
            source_type="rss",
            language="ar",
            title="اختبار البيانات الوصفية",
            url="https://example.com/meta/1",
            word_count=250,
            char_count=1500,
            has_summary=True,
            keyword_count=5,
            entity_count=3,
            chunk_count=4,
            processing_stage="bronze",
            content_hash="abc123",
        )
        tracker.track_article(record)

        # استرجاع
        retrieved = tracker.get_article("art_meta_001")
        assert retrieved is not None
        assert retrieved["article_id"] == "art_meta_001"
        assert retrieved["word_count"] == 250
        assert retrieved["processing_stage"] == "bronze"

        print(f"  ✓ MetadataTracker.track_article: {retrieved['article_id']}")
    finally:
        db_path.unlink(missing_ok=True)


def test_metadata_tracker_chunk():
    """تسجيل بيانات الـ chunks."""
    import tempfile
    from data_engine.metadata.tracker import MetadataTracker, ChunkMetadataRecord

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        tracker = MetadataTracker(db_path)
        chunks = [
            ChunkMetadataRecord(
                chunk_id=f"chk_{i:04d}",
                article_id="art_001",
                order=i,
                char_count=200 + i * 10,
                token_count=50 + i * 2,
                strategy="recursive",
            )
            for i in range(5)
        ]
        saved = tracker.track_chunks_bulk(chunks)
        assert saved == 5

        retrieved = tracker.get_chunks_for_article("art_001")
        assert len(retrieved) == 5
        assert retrieved[0]["ord"] == 0
        assert retrieved[-1]["ord"] == 4

        print(f"  ✓ MetadataTracker.track_chunks: {saved} chunks مُسجّلة")
    finally:
        db_path.unlink(missing_ok=True)


def test_metadata_tracker_stage():
    """تسجيل مراحل الـ pipeline."""
    import tempfile
    from data_engine.metadata.tracker import MetadataTracker, PipelineStageRecord

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        tracker = MetadataTracker(db_path)
        stages = ["fetch", "clean", "filter", "enrich", "transform", "store"]
        for i, stage in enumerate(stages):
            tracker.track_stage(PipelineStageRecord(
                run_id="run_001",
                stage_name=stage,
                input_count=20 - i,
                output_count=18 - i,
                rejected_count=2,
                error_count=0,
                duration_ms=50.0 + i * 10,
                source_id="ch_001",
            ))

        retrieved = tracker.get_stage_stats_for_run("run_001")
        assert len(retrieved) == 6

        perf = tracker.pipeline_performance()
        assert "fetch" in perf
        assert perf["store"]["avg_ms"] > 0

        print(f"  ✓ Pipeline stage tracking: {len(retrieved)} مراحل")
    finally:
        db_path.unlink(missing_ok=True)


def test_metadata_tracker_stats():
    """الإحصائيات الشاملة."""
    import tempfile
    from data_engine.metadata.tracker import (
        MetadataTracker, ArticleMetadataRecord, ChunkMetadataRecord
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        tracker = MetadataTracker(db_path)

        # إضافة بيانات
        for i in range(10):
            tracker.track_article(ArticleMetadataRecord(
                article_id=f"art_{i:04d}",
                source_id="ch_001",
                language="ar" if i % 2 == 0 else "en",
                processing_stage="bronze" if i < 5 else "silver",
                is_duplicate=(i >= 8),
            ))

        stats = tracker.overall_stats()
        assert stats["articles"]["total"] == 10
        assert stats["articles"]["duplicates"] == 2
        assert stats["articles"]["unique"] == 8
        assert "ar" in stats["articles"]["by_language"]
        assert "bronze" in stats["articles"]["by_stage"]

        print(f"  ✓ Overall stats: {stats['articles']['total']} مقالات, "
              f"{stats['articles']['duplicates']} مكرّرة")
    finally:
        db_path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Integration Test
# ─────────────────────────────────────────────────────────────────────────────

def test_full_pipeline_integration():
    """اختبار تكامل كامل: Article → Unified → Chunk → Dedup → Embed → Track."""
    import tempfile
    from shared.schemas.unified_article import UnifiedArticle, ArticleProcessingStage
    from data_engine.processing.transformation.chunking_engine import ChunkingEngine
    from data_engine.processing.filtering.deduplication_engine import (
        DeduplicationEngine, DeduplicationConfig
    )
    from data_engine.ai.embeddings.base_embedder import MockEmbedder, EmbeddingConfig
    from data_engine.ai.embeddings.embedding_cache import EmbeddingCache
    from data_engine.ai.embeddings.embedding_storage import EmbeddingStorage
    from data_engine.ai.embeddings.embedding_metadata import EmbeddingMetadataTracker
    from data_engine.ai.embeddings.embedding_pipeline import EmbeddingPipeline
    from data_engine.metadata.tracker import (
        MetadataTracker, ArticleMetadataRecord, ChunkMetadataRecord
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # ── 1. إنشاء مقالات ──────────────────────────────────────────────────
        old_articles = [_make_article(i) for i in range(10)]
        # إضافة مقالَيْن مكرَّرَيْن
        old_articles.extend([_make_article(0), _make_article(1)])

        # ── 2. تحويل إلى UnifiedArticle ─────────────────────────────────────
        from shared.schemas.unified_article import articles_to_unified
        unified_articles = articles_to_unified(old_articles)
        assert len(unified_articles) == 12

        # ── 3. Deduplication ─────────────────────────────────────────────────
        dedup = DeduplicationEngine(DeduplicationConfig(
            persistent=False, deduplicate_similar=False
        ))
        dedup_result = dedup.deduplicate_articles(unified_articles)
        assert dedup_result.unique_count == 10
        assert dedup_result.duplicate_count == 2

        unique_articles = dedup_result.unique_articles

        # ── 4. تحديث مرحلة المعالجة ──────────────────────────────────────────
        for art in unique_articles:
            art.advance_stage(ArticleProcessingStage.BRONZE)

        # ── 5. Chunking ───────────────────────────────────────────────────────
        engine = ChunkingEngine()
        all_chunks = []
        for art in unique_articles[:3]:  # أول 3 مقالات
            chunks = engine.chunk_article(art)
            art.mark_as_chunked([c.chunk_id for c in chunks])
            all_chunks.extend(chunks)

        assert len(all_chunks) > 0

        # ── 6. Chunk Deduplication ────────────────────────────────────────────
        chunk_dedup_result = dedup.deduplicate_chunks(all_chunks)
        assert chunk_dedup_result.unique_count > 0

        # ── 7. Embedding Pipeline ─────────────────────────────────────────────
        pipeline = EmbeddingPipeline(
            embedder=MockEmbedder(EmbeddingConfig(dimensions=64)),
            cache=EmbeddingCache(persistent=False),
            storage=EmbeddingStorage(tmp / "emb.db"),
            tracker=EmbeddingMetadataTracker(tmp / "meta.db"),
        )
        emb_result = asyncio.run(pipeline.process_chunks(
            chunk_dedup_result.unique_chunks,
            article_id=unique_articles[0].id,
        ))
        assert emb_result.total_stored > 0

        # ── 8. Metadata Tracking ──────────────────────────────────────────────
        tracker = MetadataTracker(tmp / "system_meta.db")
        for art in unique_articles:
            tracker.track_article(ArticleMetadataRecord(
                article_id=art.id,
                source_id=art.source,
                language=art.language,
                chunk_count=art.chunk_count,
                processing_stage=art.processing.processing_stage.value,
                is_duplicate=False,
            ))

        stats = tracker.overall_stats()
        assert stats["articles"]["total"] == 10

        print(
            f"\n  ✅ Integration Test كامل:\n"
            f"     • 12 مقالات → {dedup_result.unique_count} فريدة بعد الـ dedup\n"
            f"     • {len(all_chunks)} chunks → {chunk_dedup_result.unique_count} فريدة\n"
            f"     • {emb_result.total_stored} embeddings مُخزّنة\n"
            f"     • {stats['articles']['total']} مقالات في MetadataTracker\n"
            f"     • Pipeline جاهز للـ Phase 7 ✓"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

TESTS = [
    # Section 1
    ("1.1 UnifiedArticle Fields",         test_unified_article_fields),
    ("1.2 Legacy Article Conversion",     test_unified_article_from_legacy),
    ("1.3 Content & URL Hashes",          test_unified_article_hashes),
    ("1.4 Stage Progression",             test_unified_article_stage_progression),
    ("1.5 Serialization",                 test_unified_article_serialization),
    # Section 2
    ("2.1 Recursive Chunking",            test_chunking_recursive),
    ("2.2 Semantic Chunking",             test_chunking_semantic),
    ("2.3 Fixed Chunking",                test_chunking_fixed),
    ("2.4 Token-Aware Chunking",          test_chunking_token_aware),
    ("2.5 DocumentChunk Fields",          test_chunk_document_fields),
    ("2.6 Chunk Deduplicator",            test_chunk_deduplicator),
    ("2.7 Batch Chunking",                test_chunking_batch),
    # Section 3
    ("3.1 URL Deduplication",             test_dedup_url_detection),
    ("3.2 Content Deduplication",         test_dedup_content_detection),
    ("3.3 Unique Articles Pass Through",  test_dedup_unique_articles),
    ("3.4 UnifiedArticle Dedup",          test_dedup_unified_articles),
    ("3.5 Chunk Deduplication",           test_dedup_chunks),
    ("3.6 Dedup Stats",                   test_dedup_stats),
    # Section 4
    ("4.1 MockEmbedder Single",           test_mock_embedder_single),
    ("4.2 MockEmbedder Batch",            test_mock_embedder_batch),
    ("4.3 Embedding Cache",               test_embedding_cache),
    ("4.4 Embedding Storage",             test_embedding_storage),
    ("4.5 Pipeline — Chunks",             test_embedding_pipeline_chunks),
    ("4.6 Pipeline — Full Article",       test_embedding_pipeline_article),
    ("4.7 Cache Hit Rate",                test_embedding_cache_hit),
    # Section 5
    ("5.1 Article Metadata",              test_metadata_tracker_article),
    ("5.2 Chunk Metadata",                test_metadata_tracker_chunk),
    ("5.3 Pipeline Stage Metadata",       test_metadata_tracker_stage),
    ("5.4 Overall Stats",                 test_metadata_tracker_stats),
    # Section 6
    ("6.0 Full Integration",              test_full_pipeline_integration),
]


if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  Phase 6.5 — AI Data Layer Stabilization Tests")
    print("═" * 60)

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in TESTS:
        print(f"\n[{name}]")
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            import traceback
            failed += 1
            errors.append((name, str(exc)))
            print(f"  ✗ FAIL: {exc}")
            traceback.print_exc()

    print("\n" + "═" * 60)
    print(f"  النتيجة: {passed}/{len(TESTS)} اختبارات ناجحة")
    if errors:
        print(f"  الفاشلة ({failed}):")
        for name, err in errors:
            print(f"    • {name}: {err[:80]}")
    else:
        print("  ✅ جميع الاختبارات ناجحة — النظام جاهز للـ Phase 7!")
    print("═" * 60)
    sys.exit(0 if not errors else 1)
