"""
Section 7.10 — Phase 7 Integration Tests
=========================================
30 اختبار شامل لجميع مكوّنات Phase 7:
  7.1 — Embedding Models Layer
  7.2 — Chunk Embedding Pipeline
  7.3 — Vector Storage (FAISS + SQLite)
  7.4 — Semantic Search Engine
  7.5 — Retriever Layer
  7.6 — RAG Engine Foundation
  7.9 — Search Metrics
  7.10 — Full Integration
"""
from __future__ import annotations

import asyncio
import math
import sys
import time
import traceback
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── helpers ───────────────────────────────────────────────────────────────

PASS = "✓"
FAIL = "✗"
_results = []


def test(name: str):
    def decorator(fn):
        def wrapper():
            try:
                fn()
                _results.append((name, True, None))
                print(f"  {PASS} {name}")
            except Exception as exc:
                _results.append((name, False, exc))
                print(f"  {FAIL} FAIL: {exc}")
                traceback.print_exc()
        return wrapper
    return decorator


def run(coro):
    return asyncio.run(coro)


def approx(expected, abs_tol=0.01):
    """تقريب بسيط بدل pytest.approx."""
    class Approx:
        def __eq__(self, actual):
            return math.fabs(actual - expected) <= abs_tol
        def __repr__(self):
            return f"approx({expected}±{abs_tol})"
    return Approx()


# ─── Fixtures ──────────────────────────────────────────────────────────────

def _make_chunks(n: int = 10):
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy, DocumentChunk
    )
    import hashlib
    engine = ChunkingEngine(ChunkingConfig(
        strategy=ChunkingStrategy.FIXED,
        chunk_size=150,
        overlap=20,
        min_chunk_chars=30,
    ))
    texts = [
        "الذكاء الاصطناعي يُحدث ثورة في صناعة التكنولوجيا ويغيّر طريقة عملنا.",
        "تعلم الآلة هو فرع من الذكاء الاصطناعي يُمكّن الأنظمة من التعلم من البيانات.",
        "نماذج GPT وClaude غيّرت مفهوم التفاعل بين الإنسان والحاسوب الحديث.",
        "البحث الدلالي يتجاوز مطابقة الكلمات ليفهم المعنى والسياق الكامل.",
        "تخزين المتجهات يُتيح البحث السريع في ملايين الـ embeddings بكفاءة.",
        "RAG تجمع بين الاسترجاع والتوليد لإنتاج إجابات دقيقة ومدعومة بالمصادر.",
        "FAISS مكتبة Meta للبحث الفعّال في المتجهات والـ embeddings الكبيرة.",
        "النماذج اللغوية تستخدم embeddings لتمثيل النصوص في فضاء متجه.",
        "الاسترجاع المُعزَّز يُحسّن دقة النماذج اللغوية ويقلل الهلوسة.",
        "أنظمة الأسئلة والأجوبة تعتمد على البحث الدلالي لإيجاد الإجابات.",
    ]
    all_chunks = []
    for i, text in enumerate(texts[:n]):
        chunks = engine.chunk_text(text * 3, article_id=f"art_{i:04d}")
        if chunks:
            c = chunks[0]
            c.text = text
            all_chunks.append(c)
        else:
            c = DocumentChunk(
                chunk_id=f"chk_{i:04d}",
                article_id=f"art_{i:04d}",
                text=text,
                token_count=len(text.split()),
                char_count=len(text),
                order=0,
                content_hash=hashlib.md5(text.encode()).hexdigest()[:16],
            )
            all_chunks.append(c)
    return all_chunks


async def _build_search_engine(chunks):
    from core.embeddings.embedding_manager import get_embedding_manager
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    from services.search.semantic_search import SemanticSearchEngine

    manager = get_embedding_manager()
    texts = [c.text for c in chunks]
    emb_results = await manager.embed_batch(texts)

    dim = emb_results[0].dimensions if emb_results else 384
    store = FAISSVectorStore(dimensions=dim)
    entries = [
        VectorEntry(
            id=f"vec_{i}",
            vector=r.vector,
            chunk_id=chunks[i].chunk_id,
            article_id=chunks[i].article_id,
            text=chunks[i].text,
            model_name=r.model_name,
            metadata={
                "url": f"https://example.com/{chunks[i].article_id}",
                "title": f"مقال {chunks[i].article_id}",
            },
        )
        for i, r in enumerate(emb_results)
    ]
    store.add(entries)
    engine = SemanticSearchEngine(vector_store=store, rerank=True)
    return engine


# ═══════════════════════════════════════════════════════════════════════════
# Section 7.1 — Embedding Models Layer
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print("  Phase 7 — Vector Search + RAG Foundation Tests")
print("═" * 60)

print("\n[7.1 Embedding Models Layer]")


@test("7.1.1 EmbeddingConfig defaults")
def test_embedding_config():
    from core.embeddings.base import EmbeddingConfig
    cfg = EmbeddingConfig()
    assert cfg.dimensions == 384
    assert cfg.batch_size == 32
    assert cfg.normalize_embeddings is True
test_embedding_config()


@test("7.1.2 SentenceTransformer load & embed")
def test_st_embed():
    from core.embeddings.sentence_transformer import SentenceTransformerModel
    model = SentenceTransformerModel()
    result = run(model.embed("اختبار النموذج الحقيقي"))
    assert len(result.vector) > 0
    assert result.dimensions > 0
    print(f"     → dims={result.dimensions} latency={result.latency_ms:.1f}ms", end="")
test_st_embed()


@test("7.1.3 Batch Embedding (10 texts)")
def test_st_batch():
    from core.embeddings.sentence_transformer import SentenceTransformerModel
    model = SentenceTransformerModel()
    texts = [f"نص رقم {i} للاختبار" for i in range(10)]
    results = run(model.embed_batch(texts))
    assert len(results) == 10
    assert all(len(r.vector) == results[0].dimensions for r in results)
    print(f"     → {len(results)} embeddings, dims={results[0].dimensions}", end="")
test_st_batch()


@test("7.1.4 EmbeddingRegistry.list_models()")
def test_registry():
    from core.embeddings.embedding_registry import EmbeddingRegistry
    models = EmbeddingRegistry.list_models()
    assert len(models) >= 1
    assert "all-MiniLM-L6-v2" in models
test_registry()


@test("7.1.5 EmbeddingManager singleton + health_check")
def test_manager_health():
    from core.embeddings.embedding_manager import get_embedding_manager
    m1 = get_embedding_manager()
    m2 = get_embedding_manager()
    assert m1 is m2
    health = run(m1.health_check())
    assert health["status"] == "ok"
    assert health["dimensions"] > 0
    print(f"     → {health['dimensions']} dims", end="")
test_manager_health()


@test("7.1.6 Embed 100 texts — performance")
def test_embed_100():
    from core.embeddings.embedding_manager import get_embedding_manager
    manager = get_embedding_manager()
    texts = [f"نص رقم {i} لقياس الأداء في توليد الـ embeddings" for i in range(100)]
    t0 = time.perf_counter()
    results = run(manager.embed_batch(texts))
    ms = (time.perf_counter() - t0) * 1000
    assert len(results) == 100
    print(f"     → 100 embeddings في {ms:.0f}ms ({ms/100:.1f}ms/text)", end="")
test_embed_100()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.2 — Chunk Embedding Pipeline
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.2 Chunk Embedding Pipeline]")


@test("7.2.1 ChunkEmbeddingStage — single chunk")
def test_embed_stage_single():
    from data_engine.pipelines.stages.embed_stage import ChunkEmbeddingStage
    chunks = _make_chunks(1)
    stage = ChunkEmbeddingStage()
    record = run(stage.process_single(chunks[0], chunks[0].article_id))
    assert record is not None
    assert len(record.vector) > 0
    assert record.embedding_dim > 0
test_embed_stage_single()


@test("7.2.2 ChunkEmbeddingStage — batch 10 chunks")
def test_embed_stage_batch():
    from data_engine.pipelines.stages.embed_stage import ChunkEmbeddingStage
    chunks = _make_chunks(10)
    stage = ChunkEmbeddingStage(batch_size=5)
    result = run(stage.process(chunks, "article_batch"))
    assert result.embedded == 10
    assert result.failed == 0
    assert len(result.records) == 10
    print(f"     → {result.embedded} embedded في {result.total_ms:.1f}ms", end="")
test_embed_stage_batch()


@test("7.2.3 ChunkEmbeddingRecord fields")
def test_embed_record_fields():
    from data_engine.pipelines.stages.embed_stage import ChunkEmbeddingStage
    chunks = _make_chunks(1)
    stage = ChunkEmbeddingStage()
    result = run(stage.process(chunks, "art_001"))
    record = result.records[0]
    assert record.chunk_id
    assert record.article_id == "art_001"
    assert record.model_name != ""
    assert record.embedding_dim > 0
    assert record.latency_ms >= 0
test_embed_record_fields()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.3 — Vector Storage (FAISS + SQLite)
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.3 Vector Storage Layer — FAISS]")


@test("7.3.1 FAISSVectorStore — add 100 vectors")
def test_faiss_add():
    import numpy as np
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    rng = np.random.default_rng(0)
    store = FAISSVectorStore(dimensions=64)
    entries = [
        VectorEntry(
            id=f"v{i}",
            vector=(rng.standard_normal(64) / (np.linalg.norm(rng.standard_normal(64)) + 1e-9)).tolist(),
            chunk_id=f"chk_{i}", article_id=f"art_{i % 10}",
            text=f"نص {i}", model_name="test",
        )
        for i in range(100)
    ]
    added = store.add(entries)
    assert added == 100
    assert store.stats().total_vectors == 100
    print(f"     → {store.stats().total_vectors} vectors في FAISS", end="")
test_faiss_add()


@test("7.3.2 FAISSVectorStore — similarity search top-5")
def test_faiss_search():
    import numpy as np
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    rng = np.random.default_rng(42)
    store = FAISSVectorStore(dimensions=32)
    entries = [
        VectorEntry(id=f"v{i}", vector=rng.standard_normal(32).tolist(),
                    chunk_id=f"chk_{i}", article_id=f"art_{i}", text=f"نص {i}", model_name="t")
        for i in range(50)
    ]
    store.add(entries)
    query = rng.standard_normal(32).tolist()
    results = store.search(query, top_k=5)
    assert len(results) == 5
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    print(f"     → top-5: {[round(s,3) for s in scores[:3]]}", end="")
test_faiss_search()


@test("7.3.3 FAISSVectorStore — save & load")
def test_faiss_save_load():
    import tempfile, os
    import numpy as np
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    store = FAISSVectorStore(dimensions=16)
    rng = np.random.default_rng(1)
    entries = [
        VectorEntry(id=f"v{i}", vector=rng.standard_normal(16).tolist(),
                    chunk_id=f"c{i}", article_id="art_0", text=f"t{i}", model_name="m")
        for i in range(10)
    ]
    store.add(entries)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "idx")
        store.save(path)
        store2 = FAISSVectorStore(dimensions=16)
        store2.load(path)
        assert store2.stats().total_vectors == 10
test_faiss_save_load()


@test("7.3.4 SQLiteVectorIndex — add & cosine search")
def test_sqlite_vector():
    import tempfile
    import numpy as np
    from data_engine.storage.vector_store.sqlite_vector_index import SQLiteVectorIndex
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    rng = np.random.default_rng(0)
    with tempfile.TemporaryDirectory() as td:
        store = SQLiteVectorIndex(db_path=f"{td}/test_vec.db")
        entries = [
            VectorEntry(id=f"sv{i}", vector=rng.standard_normal(32).tolist(),
                        chunk_id=f"c{i}", article_id=f"a{i}", text=f"t {i}", model_name="m")
            for i in range(20)
        ]
        store.add(entries)
        q = rng.standard_normal(32).tolist()
        results = store.search(q, top_k=5)
        assert len(results) == 5
test_sqlite_vector()


@test("7.3.5 FAISSVectorStore — metadata filtering")
def test_faiss_filter():
    import numpy as np
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    rng = np.random.default_rng(7)
    store = FAISSVectorStore(dimensions=16)
    for i in range(20):
        cat = "ai" if i < 10 else "news"
        e = VectorEntry(id=f"v{i}", vector=rng.standard_normal(16).tolist(),
                        chunk_id=f"c{i}", article_id=f"a{i}", text=f"t{i}",
                        model_name="m", metadata={"category": cat})
        store.add([e])
    q = rng.standard_normal(16).tolist()
    results = store.search(q, top_k=5, filter_metadata={"category": "ai"})
    assert all(r.metadata.get("category") == "ai" for r in results)
test_faiss_filter()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.4 — Semantic Search Engine
# (نبني engine مشترك)
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.4 Semantic Search Engine]")

_CHUNKS = _make_chunks(10)
_ENGINE = run(_build_search_engine(_CHUNKS))


@test("7.4.1 QueryProcessor — Arabic question detection")
def test_query_processor():
    from services.search.query_processor import QueryProcessor
    qp = QueryProcessor()
    result = qp.process("ما هو الذكاء الاصطناعي؟")
    assert result.is_question is True
    assert result.language == "ar"
    assert len(result.keywords) > 0
test_query_processor()


@test("7.4.2 SemanticSearchEngine — basic search")
def test_semantic_search_basic():
    response = run(_ENGINE.search("الذكاء الاصطناعي", top_k=3))
    assert response.total_found > 0
    assert response.search_time_ms > 0
    assert len(response.hits) <= 3
    print(f"     → {response.total_found} نتيجة في {response.search_time_ms:.1f}ms", end="")
test_semantic_search_basic()


@test("7.4.3 SearchResponse fields validation")
def test_search_response_fields():
    response = run(_ENGINE.search("تعلم الآلة", top_k=5))
    assert response.query == "تعلم الآلة"
    assert response.model_name != ""
    assert len(response.query_vector_preview) > 0
    for hit in response.hits:
        assert hit.chunk_id
        assert hit.article_id
        assert hit.score >= 0
test_search_response_fields()


@test("7.4.4 Reranker — diversity penalty")
def test_reranker():
    from services.search.reranker import Reranker
    from data_engine.storage.vector_store.base_vector_store import SearchResult
    reranker = Reranker(max_per_article=2)
    raw = [
        SearchResult(chunk_id=f"c{i}", article_id="art_0" if i < 5 else f"art_{i}",
                     score=0.9 - i * 0.05, text="نص " * 30)
        for i in range(10)
    ]
    reranked = reranker.rerank(raw, top_k=5)
    assert len(reranked) == 5
    art0_count = sum(1 for r in reranked if r.article_id == "art_0")
    assert art0_count <= 2
test_reranker()


@test("7.4.5 Hybrid Search")
def test_hybrid_search():
    response = run(_ENGINE.hybrid_search("FAISS vector", top_k=5))
    assert response.search_type == "hybrid"
    assert response.total_found > 0
test_hybrid_search()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.5 — Retriever Layer
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.5 Retriever Layer]")


@test("7.5.1 VectorRetriever — retrieve top-5")
def test_vector_retriever():
    from services.retrieval.vector_retriever import VectorRetriever
    retriever = VectorRetriever(_ENGINE)
    result = run(retriever.retrieve("نماذج اللغة الكبيرة", top_k=5))
    assert result.total_retrieved > 0
    assert result.retriever_name == "VectorRetriever"
    print(f"     → {result.total_retrieved} chunks في {result.retrieval_time_ms:.1f}ms", end="")
test_vector_retriever()


@test("7.5.2 HybridRetriever")
def test_hybrid_retriever():
    from services.retrieval.hybrid_retriever import HybridRetriever
    retriever = HybridRetriever(_ENGINE, semantic_weight=0.8)
    result = run(retriever.retrieve("RAG استرجاع", top_k=5))
    assert result.retriever_name == "HybridRetriever"
    assert result.total_retrieved > 0
test_hybrid_retriever()


@test("7.5.3 MultiQueryRetriever — variant generation")
def test_multi_query_retriever():
    from services.retrieval.multi_query_retriever import MultiQueryRetriever
    retriever = MultiQueryRetriever(_ENGINE, num_queries=3, per_query_k=3)
    result = run(retriever.retrieve("الذكاء الاصطناعي", top_k=5))
    assert result.retriever_name == "MultiQueryRetriever"
    assert result.metadata.get("num_variants", 0) >= 1
    print(f"     → {result.metadata.get('num_variants')} variants → {result.total_retrieved} chunks", end="")
test_multi_query_retriever()


@test("7.5.4 ContextAssembler — build context")
def test_context_assembler():
    from services.retrieval.vector_retriever import VectorRetriever
    from services.retrieval.context_assembler import ContextAssembler
    retriever = VectorRetriever(_ENGINE)
    retrieval_result = run(retriever.retrieve("البحث الدلالي", top_k=5))
    assembler = ContextAssembler(max_context_chars=3000)
    context = assembler.assemble(retrieval_result)
    assert len(context.context_text) > 0
    assert context.query == "البحث الدلالي"
    print(f"     → {len(context.context_text)} حرف", end="")
test_context_assembler()


@test("7.5.5 RetrievalResult.to_context_text()")
def test_retrieval_to_text():
    from services.retrieval.vector_retriever import VectorRetriever
    retriever = VectorRetriever(_ENGINE)
    result = run(retriever.retrieve("embeddings", top_k=3))
    text = result.to_context_text()
    assert isinstance(text, str)
    assert len(text) > 0
test_retrieval_to_text()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.6 — RAG Pipeline
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.6 RAG Pipeline]")


def _make_rag_pipeline():
    from services.retrieval.vector_retriever import VectorRetriever
    from services.rag.rag_pipeline import RAGPipeline
    return RAGPipeline(retriever=VectorRetriever(_ENGINE))


_RAG = _make_rag_pipeline()


@test("7.6.1 RAGPipeline — basic run")
def test_rag_basic():
    from services.rag.rag_pipeline import RAGRequest
    req = RAGRequest(query="ما هو الذكاء الاصطناعي؟", top_k=3)
    response = run(_RAG.run(req))
    assert response.total_ms > 0
    assert len(response.formatted.context_used) > 0
    assert len(response.formatted.prompt_ready) > 100
    print(f"     → {len(response.formatted.citations)} مصادر، context={len(response.formatted.context_used)} حرف", end="")
test_rag_basic()


@test("7.6.2 RAGPipeline — stage timings present")
def test_rag_timings():
    from services.rag.rag_pipeline import RAGRequest
    req = RAGRequest(query="FAISS search", top_k=3)
    response = run(_RAG.run(req))
    assert "retrieval_ms" in response.stage_timings
    assert "prompt_build_ms" in response.stage_timings
    assert all(v >= 0 for v in response.stage_timings.values())
test_rag_timings()


@test("7.6.3 ContextBuilder — token limit respected")
def test_context_builder():
    from services.retrieval.vector_retriever import VectorRetriever
    from services.retrieval.context_assembler import ContextAssembler
    from services.rag.context_builder import ContextBuilder
    retriever = VectorRetriever(_ENGINE)
    result = run(retriever.retrieve("البحث", top_k=5))
    assembled = ContextAssembler().assemble(result)
    builder = ContextBuilder(max_tokens=50)
    built = builder.build(assembled)
    assert built.total_tokens_estimate <= 50
test_context_builder()


@test("7.6.4 PromptBuilder — Arabic QA template")
def test_prompt_builder():
    from services.retrieval.vector_retriever import VectorRetriever
    from services.retrieval.context_assembler import ContextAssembler
    from services.rag.context_builder import ContextBuilder
    from services.rag.prompt_builder import PromptBuilder
    retriever = VectorRetriever(_ENGINE)
    result = run(retriever.retrieve("الذكاء", top_k=3))
    assembled = ContextAssembler().assemble(result)
    built = ContextBuilder().build(assembled)
    builder = PromptBuilder()
    prompt = builder.build("ما هو الذكاء الاصطناعي؟", built, language="ar")
    assert len(prompt.prompt) > 50
    assert prompt.template_used != ""
    assert "ما هو" in prompt.prompt
test_prompt_builder()


@test("7.6.5 CitationManager — format references")
def test_citation_manager():
    from services.rag.citation_manager import CitationManager
    mgr = CitationManager()
    chunks = [
        {"chunk_id": f"c{i}", "article_id": f"art_{i}",
         "source_url": f"https://ex.com/{i}", "source_title": f"مقال {i}",
         "text": "نص " * 20, "score": 0.9 - i * 0.1}
        for i in range(3)
    ]
    mgr.add_from_chunks(chunks)
    assert len(mgr.get_all()) == 3
    assert "المصادر" in mgr.format_references()
test_citation_manager()


@test("7.6.6 RAGPipeline.quick_context()")
def test_rag_quick_context():
    context = run(_RAG.quick_context("تخزين المتجهات", top_k=3))
    assert isinstance(context, str)
    assert len(context) > 0
test_rag_quick_context()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.9 — Search Metrics
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.9 Search Metrics & Evaluation]")


@test("7.9.1 LatencyTracker — record & stats")
def test_latency_tracker():
    from monitoring.search_metrics.latency_tracker import LatencyTracker
    tracker = LatencyTracker(window_size=100)
    for ms in [10.0, 20.0, 30.0, 40.0, 50.0]:
        tracker.record("search", ms)
    stats = tracker.stats("search")
    assert stats["count"] == 5
    assert stats["mean_ms"] == approx(30.0, abs_tol=0.01)
    assert stats["min_ms"] == approx(10.0, abs_tol=0.01)
test_latency_tracker()


@test("7.9.2 RetrievalEvaluator — precision & recall")
def test_retrieval_evaluator():
    from monitoring.search_metrics.retrieval_evaluator import RetrievalEvaluator
    ev = RetrievalEvaluator()
    retrieved = ["a", "b", "c", "d", "e"]
    relevant = ["a", "c", "e"]
    result = ev.evaluate("اختبار", retrieved, relevant_ids=relevant, k=5)
    assert result.precision_at_k == approx(3/5)
    assert result.recall_at_k == approx(3/3)
    assert result.mrr > 0
test_retrieval_evaluator()


@test("7.9.3 RetrievalEvaluator — duplicate detection")
def test_dup_rate():
    from monitoring.search_metrics.retrieval_evaluator import RetrievalEvaluator
    ev = RetrievalEvaluator()
    result = ev.evaluate("q", ["a", "a", "b", "b", "c"])
    assert result.duplicate_rate == approx(0.4)
test_dup_rate()


@test("7.9.4 SearchMetricsCollector — summary")
def test_metrics_collector():
    from monitoring.search_metrics.metrics_collector import SearchMetricsCollector
    coll = SearchMetricsCollector()
    for i in range(5):
        coll.record_search(f"query {i}", latency_ms=15 + i, num_results=10)
    coll.record_embedding(num_texts=32, latency_ms=50.0)
    coll.record_rag(latency_ms=200.0, num_citations=3)
    summary = coll.summary()
    assert summary["counters"]["search.semantic"] == 5
    assert "latency_per_operation" in summary
test_metrics_collector()


@test("7.9.5 RetrievalEvaluator — batch evaluation")
def test_batch_eval():
    from monitoring.search_metrics.retrieval_evaluator import RetrievalEvaluator
    ev = RetrievalEvaluator()
    queries = [
        {"query": f"q{i}", "retrieved_ids": [f"r{j}" for j in range(5)],
         "relevant_ids": [f"r{j}" for j in range(3)]}
        for i in range(10)
    ]
    metrics = ev.batch_evaluate(queries)
    assert metrics["num_queries"] == 10
    assert "mean_ndcg" in metrics
test_batch_eval()

# ═══════════════════════════════════════════════════════════════════════════
# Section 7.10 — Full Integration
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n[7.10 Full Integration — End-to-End]")


@test("7.10.1 Full pipeline: chunks → embed → FAISS → search")
def test_full_pipeline():
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy
    )
    from data_engine.pipelines.stages.embed_stage import ChunkEmbeddingStage
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry
    from services.search.semantic_search import SemanticSearchEngine

    async def _run():
        engine = ChunkingEngine(ChunkingConfig(
            strategy=ChunkingStrategy.RECURSIVE,
            chunk_size=300, overlap=30, min_chunk_chars=50,
        ))
        demo_texts = [
            "الذكاء الاصطناعي يُحدث ثورة شاملة في قطاعات الصناعة والتكنولوجيا والرعاية الصحية.",
            "تعلم الآلة Deep Learning يُمكّن الحواسيب من التعلم الذاتي دون برمجة صريحة.",
            "نماذج GPT وClaude تمثّل قفزة نوعية في قدرات الذكاء الاصطناعي التوليدي.",
            "FAISS وQdrant مكتبتان للبحث الفعّال في فضاء المتجهات.",
            "RAG يُحسّن دقة النماذج اللغوية ويقلّل الهلوسة بشكل كبير جداً.",
        ] * 4
        all_chunks = []
        for i, text in enumerate(demo_texts):
            chunks = engine.chunk_text(text, article_id=f"full_{i:02d}")
            if chunks:
                all_chunks.append(chunks[0])
        assert len(all_chunks) > 0

        stage = ChunkEmbeddingStage()
        embed_result = await stage.process(all_chunks, "batch_article")
        assert embed_result.embedded > 0

        dim = embed_result.records[0].embedding_dim
        store = FAISSVectorStore(dimensions=dim)
        entries = [
            VectorEntry(id=f"vec_{r.chunk_id}", vector=r.vector,
                        chunk_id=r.chunk_id, article_id=r.article_id,
                        text=r.text, model_name=r.model_name)
            for r in embed_result.records
        ]
        store.add(entries)
        assert store.stats().total_vectors == embed_result.embedded

        search_engine = SemanticSearchEngine(vector_store=store)
        response = await search_engine.search("ما آخر أخبار الذكاء الاصطناعي؟", top_k=5)
        assert response.total_found > 0
        assert response.hits[0].score > 0

        print(
            f"\n     ✅ Pipeline كامل:"
            f"\n       • {len(all_chunks)} chunks → {embed_result.embedded} embeddings"
            f"\n       • FAISS: {store.stats().total_vectors} vectors ({dim} dims)"
            f"\n       • بحث → {response.total_found} نتيجة (top: {response.hits[0].score:.4f})",
            end=""
        )

    run(_run())
test_full_pipeline()


@test("7.10.2 Full RAG pipeline end-to-end")
def test_full_rag():
    from services.retrieval.multi_query_retriever import MultiQueryRetriever
    from services.rag.rag_pipeline import RAGPipeline, RAGRequest

    retriever = MultiQueryRetriever(_ENGINE, num_queries=2, per_query_k=3)
    rag = RAGPipeline(retriever=retriever)
    req = RAGRequest(query="ما آخر أخبار الذكاء الاصطناعي؟", top_k=5, language="ar")
    response = run(rag.run(req))
    fd = response.formatted
    assert len(fd.prompt_ready) > 200
    assert len(fd.citations) > 0
    assert "السياق" in fd.prompt_ready or "Question" in fd.prompt_ready or "السؤال" in fd.prompt_ready

    print(
        f"\n     ✅ RAG Pipeline:"
        f"\n       • {len(fd.citations)} مصادر"
        f"\n       • context: {len(fd.context_used)} حرف"
        f"\n       • prompt: {len(fd.prompt_ready)} حرف"
        f"\n       • الوقت الكلي: {response.total_ms:.1f}ms"
        f"\n       • جاهز للـ LLM ✓",
        end=""
    )
test_full_rag()

# ═══════════════════════════════════════════════════════════════════════════
# النتائج
# ═══════════════════════════════════════════════════════════════════════════

total = len(_results)
passed = sum(1 for _, ok, _ in _results if ok)
failed_list = [(name, err) for name, ok, err in _results if not ok]

print(f"\n\n{'═'*60}")
print(f"  النتيجة: {passed}/{total} اختبارات ناجحة")
if failed_list:
    print(f"  الفاشلة ({len(failed_list)}):")
    for name, err in failed_list:
        print(f"    • {name}: {err}")
else:
    print(f"  ✅ جميع الاختبارات ناجحة — Phase 7 جاهز للـ LLM!")
print("═" * 60)

sys.exit(0 if not failed_list else 1)
