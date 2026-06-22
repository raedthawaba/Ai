"""
demo_rag.py — عرض توضيحي كامل لـ Phase 7

يُنفّذ السيناريو الكامل:
  1. تحميل نصوص تجريبية (أخبار الذكاء الاصطناعي)
  2. تقطيع (Chunking)
  3. توليد Embeddings حقيقية (sentence-transformers)
  4. فهرسة في FAISS Vector Store
  5. بحث دلالي (Semantic Search)
  6. RAG Pipeline كامل
  7. عرض النتائج

تشغيل:
  cd hajeen_platform
  PYTHONPATH=. python demo_rag.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


DEMO_ARTICLES = [
    {
        "id": "art_001",
        "title": "ثورة الذكاء الاصطناعي في 2025",
        "text": (
            "الذكاء الاصطناعي يُحدث ثورة شاملة في جميع قطاعات الصناعة والمجتمع. "
            "نماذج اللغة الكبيرة مثل GPT-4 وClaude وGemini أصبحت قادرة على فهم "
            "وتوليد النصوص بمستوى يضاهي الإنسان في كثير من المجالات. "
            "شركات التكنولوجيا الكبرى تُضخّ مليارات الدولارات في أبحاث الذكاء الاصطناعي. "
            "المؤسسات التعليمية تُعيد تصميم مناهجها لمواكبة هذه الثورة التكنولوجية."
        ),
    },
    {
        "id": "art_002",
        "title": "تعلم الآلة وتطبيقاته العملية",
        "text": (
            "تعلم الآلة Machine Learning هو فرع أساسي من فروع الذكاء الاصطناعي. "
            "يُمكّن الأنظمة من التعلم والتحسّن من التجربة دون برمجة صريحة. "
            "تطبيقاته تشمل: التشخيص الطبي، والتنبؤ المالي، وقيادة السيارات ذاتياً. "
            "الشبكات العصبية العميقة Deep Learning حقّقت نتائج غير مسبوقة في معالجة الصور والصوت."
        ),
    },
    {
        "id": "art_003",
        "title": "Vector Databases والبحث الدلالي",
        "text": (
            "قواعد بيانات المتجهات Vector Databases أصبحت ركيزة أساسية في تطبيقات الذكاء الاصطناعي. "
            "FAISS من Meta وQdrant وPinecone هي الأبرز في هذا المجال. "
            "تُخزّن هذه القواعد النصوص كمتجهات رقمية وتُتيح البحث بالمعنى لا بالكلمات. "
            "Semantic Search يُعيد نتائج ذات صلة حتى لو لم تتطابق الكلمات بالضبط."
        ),
    },
    {
        "id": "art_004",
        "title": "RAG — الاسترجاع المُعزَّز للتوليد",
        "text": (
            "RAG Retrieval Augmented Generation تقنية ثورية تجمع بين قوة الاسترجاع ودقة التوليد. "
            "تعمل عبر ثلاث مراحل: استرجاع المعلومات ذات الصلة، وبناء السياق، وتوليد الإجابة. "
            "تُقلّل هلوسة النماذج وتُحسّن دقتها بشكل كبير لأنها تستند إلى مصادر حقيقية. "
            "تُستخدم على نطاق واسع في أنظمة الأسئلة والأجوبة وروبوتات الدردشة المؤسسية."
        ),
    },
    {
        "id": "art_005",
        "title": "Embeddings — تمثيل النصوص رياضياً",
        "text": (
            "Embeddings هي تمثيلات رياضية للنصوص في فضاء متجه عالي الأبعاد. "
            "النصوص المتشابهة في المعنى تكون قريبة في هذا الفضاء المتجهي. "
            "نموذج all-MiniLM-L6-v2 يُنتج متجهات بـ 384 بُعداً بكفاءة عالية. "
            "Cosine Similarity تُقيس التشابه بين المتجهات بدرجة دقة عالية جداً."
        ),
    },
    {
        "id": "art_006",
        "title": "أخبار OpenAI و GPT-5",
        "text": (
            "OpenAI أعلنت عن خارطة طريق طموحة لنماذجها القادمة في 2025 و2026. "
            "GPT-5 المتوقع يَعِد بتحسينات جوهرية في الاستدلال والتخطيط. "
            "المنافسة بين OpenAI وGoogle وAnthropic وMeta تُسرّع وتيرة الابتكار. "
            "النماذج متعددة الوسائط تجمع بين النص والصورة والصوت في نظام موحّد."
        ),
    },
    {
        "id": "art_007",
        "title": "تأثير الذكاء الاصطناعي على سوق العمل",
        "text": (
            "دراسات عديدة تتوقع أن الذكاء الاصطناعي سيُؤثّر على 40% من الوظائف الحالية. "
            "بعض المهن ستختفي لكن وظائف جديدة ستنشأ مرتبطة بتطوير وإدارة أنظمة الذكاء الاصطناعي. "
            "مهارات prompt engineering وفهم النماذج اللغوية أصبحت مطلوبة بشدة. "
            "الدول تسابق بعضها لوضع استراتيجيات وطنية للذكاء الاصطناعي."
        ),
    },
    {
        "id": "art_008",
        "title": "أخلاقيات الذكاء الاصطناعي",
        "text": (
            "أخلاقيات الذكاء الاصطناعي AI Ethics أصبحت مجالاً بحثياً مستقلاً ومتنامياً. "
            "التحيّز في النماذج Bias والشفافية Transparency والمساءلة Accountability قضايا جوهرية. "
            "الاتحاد الأوروبي أصدر قانون الذكاء الاصطناعي AI Act لتنظيم استخدامه. "
            "المجتمع الدولي يُناقش أُطراً تنظيمية لضمان استخدام آمن ومسؤول."
        ),
    },
    {
        "id": "art_009",
        "title": "الحوسبة الكمومية والذكاء الاصطناعي",
        "text": (
            "الحوسبة الكمومية Quantum Computing ستُحوّل قدرات الذكاء الاصطناعي جذرياً. "
            "Google وIBM وMicrosoft تتسابق على بناء حاسبات كمومية مستقرة. "
            "الخوارزميات الكمومية قادرة على معالجة بعض المسائل بسرعة تفوق الحواسيب الكلاسيكية بملايين المرات. "
            "التقاء الكمومي والذكاء الاصطناعي سيفتح آفاقاً جديدة في الاكتشاف العلمي."
        ),
    },
    {
        "id": "art_010",
        "title": "مستقبل الذكاء الاصطناعي العام AGI",
        "text": (
            "الذكاء الاصطناعي العام Artificial General Intelligence AGI هو الهدف النهائي للبحث في هذا المجال. "
            "يُقصد به نظام قادر على أداء أي مهمة فكرية يستطيعها الإنسان. "
            "العلماء منقسمون حول متى سيتحقق AGI — بعضهم يتوقع عقوداً والآخر عقداً واحداً. "
            "الاستعداد للتعامل مع AGI الآمن والمفيد يُعدّ أحد أكبر تحديات عصرنا."
        ),
    },
]


async def run_demo():
    print("\n" + "═" * 65)
    print("  🔥 Hajeen AI Platform — Phase 7 Demo")
    print("  Vector Search + RAG Foundation")
    print("═" * 65)

    # ── 1. Chunking ──────────────────────────────────────────────────────
    print("\n📦 [1/7] Chunking المقالات...")
    from data_engine.processing.transformation.chunking_engine import (
        ChunkingEngine, ChunkingConfig, ChunkingStrategy
    )
    engine = ChunkingEngine(ChunkingConfig(
        strategy=ChunkingStrategy.RECURSIVE,
        chunk_size=250,
        overlap=30,
        min_chunk_chars=50,
    ))
    all_chunks = []
    for art in DEMO_ARTICLES:
        chunks = engine.chunk_text(art["text"], article_id=art["id"])
        for c in chunks:
            c.text = c.text  # keep as-is
            # ربط metadata المقال
        all_chunks.extend(chunks or [])
    print(f"  ✓ {len(DEMO_ARTICLES)} مقال → {len(all_chunks)} chunk")

    # ── 2. Embedding ──────────────────────────────────────────────────────
    print("\n🧠 [2/7] توليد Embeddings (sentence-transformers/all-MiniLM-L6-v2)...")
    from data_engine.pipelines.stages.embed_stage import ChunkEmbeddingStage
    stage = ChunkEmbeddingStage(batch_size=32)
    t0 = time.perf_counter()
    embed_result = await stage.process(all_chunks, "demo_batch")
    embed_ms = (time.perf_counter() - t0) * 1000
    print(f"  ✓ {embed_result.embedded} embeddings في {embed_ms:.0f}ms")
    print(f"  ✓ النموذج: {embed_result.records[0].model_name if embed_result.records else 'N/A'}")
    print(f"  ✓ الأبعاد: {embed_result.records[0].embedding_dim if embed_result.records else 0}")

    # ── 3. FAISS Indexing ─────────────────────────────────────────────────
    print("\n📊 [3/7] فهرسة في FAISS Vector Store...")
    from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
    from data_engine.storage.vector_store.base_vector_store import VectorEntry

    dim = embed_result.records[0].embedding_dim
    vector_store = FAISSVectorStore(dimensions=dim)

    # جمع metadata المقالات
    art_meta = {a["id"]: {"url": f"https://hajeen.ai/{a['id']}", "title": a["title"]}
                for a in DEMO_ARTICLES}

    entries = [
        VectorEntry(
            id=f"vec_{r.chunk_id}",
            vector=r.vector,
            chunk_id=r.chunk_id,
            article_id=r.article_id,
            text=r.text,
            model_name=r.model_name,
            metadata=art_meta.get(r.article_id, {}),
        )
        for r in embed_result.records
    ]
    added = vector_store.add(entries)
    stats = vector_store.stats()
    print(f"  ✓ {added} vectors مُضافة → {stats.total_vectors} في الـ index")
    print(f"  ✓ نوع الـ index: {stats.index_type}")

    # ── 4. Semantic Search ────────────────────────────────────────────────
    print("\n🔍 [4/7] Semantic Search...")
    from services.search.semantic_search import SemanticSearchEngine
    search_engine = SemanticSearchEngine(vector_store=vector_store, rerank=True)

    queries = [
        "ما آخر أخبار الذكاء الاصطناعي؟",
        "كيف تعمل RAG Retrieval Augmented Generation؟",
        "FAISS vector search",
        "مستقبل العمل مع الذكاء الاصطناعي",
    ]

    for query in queries:
        t0 = time.perf_counter()
        response = await search_engine.search(query, top_k=3)
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n  🔎 '{query}'")
        print(f"     → {response.total_found} نتيجة في {ms:.1f}ms")
        for hit in response.hits[:2]:
            title = hit.source_title or hit.article_id
            print(f"     [{hit.rank}] score={hit.score:.4f} — {title}")
            print(f"          '{hit.text[:80]}...'")

    # ── 5. Retriever ──────────────────────────────────────────────────────
    print("\n📡 [5/7] Retriever Layer...")
    from services.retrieval.vector_retriever import VectorRetriever
    from services.retrieval.multi_query_retriever import MultiQueryRetriever

    multi_retriever = MultiQueryRetriever(search_engine, num_queries=3, per_query_k=3)
    query = "ما آخر أخبار الذكاء الاصطناعي؟"
    result = await multi_retriever.retrieve(query, top_k=5)
    print(f"  ✓ MultiQueryRetriever: {result.metadata.get('num_variants')} variants")
    print(f"  ✓ {result.total_retrieved} chunks مُسترجَعة في {result.retrieval_time_ms:.1f}ms")

    # ── 6. RAG Pipeline ───────────────────────────────────────────────────
    print("\n🤖 [6/7] RAG Pipeline كامل...")
    from services.rag.rag_pipeline import RAGPipeline, RAGRequest

    rag = RAGPipeline(retriever=VectorRetriever(search_engine))
    req = RAGRequest(
        query="ما آخر أخبار الذكاء الاصطناعي؟",
        top_k=5,
        language="ar",
        max_context_tokens=1500,
    )
    rag_response = await rag.run(req)
    fd = rag_response.formatted

    print(f"  ✓ RAG مكتمل في {rag_response.total_ms:.1f}ms")
    print(f"  ✓ مراحل:")
    for stage, ms in rag_response.stage_timings.items():
        print(f"     • {stage}: {ms:.1f}ms")
    print(f"  ✓ Context: {len(fd.context_used)} حرف")
    print(f"  ✓ مصادر: {len(fd.citations)}")
    print(f"  ✓ Prompt جاهز للـ LLM: {len(fd.prompt_ready)} حرف")

    print(f"\n  📄 معاينة الـ Prompt:")
    print("  " + "─" * 50)
    print(fd.prompt_ready[:600])
    print("  " + "─" * 50)
    print(f"  [... مقتطف، الـ prompt الكامل: {len(fd.prompt_ready)} حرف]")

    # ── 7. Search Metrics ────────────────────────────────────────────────
    print("\n📈 [7/7] Search Metrics...")
    from monitoring.search_metrics.metrics_collector import SearchMetricsCollector
    coll = SearchMetricsCollector()
    for q in queries:
        t0 = time.perf_counter()
        r = await search_engine.search(q, top_k=5)
        ms = (time.perf_counter() - t0) * 1000
        coll.record_search(q, latency_ms=ms, num_results=r.total_found)
    coll.record_rag(rag_response.total_ms, len(fd.citations))
    summary = coll.summary()
    search_stats = summary["latency_per_operation"].get("search.semantic", {})
    print(f"  ✓ {summary['counters'].get('search.semantic', 0)} عمليات بحث")
    if search_stats.get("count", 0) > 0:
        print(f"  ✓ متوسط زمن البحث: {search_stats.get('mean_ms', 0):.1f}ms")
        print(f"  ✓ P95: {search_stats.get('p95_ms', 0):.1f}ms")

    # ── الملخص النهائي ───────────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  ✅ Phase 7 Demo اكتمل بنجاح!")
    print(f"  📊 الإحصائيات:")
    print(f"     • مقالات: {len(DEMO_ARTICLES)}")
    print(f"     • Chunks: {len(all_chunks)}")
    print(f"     • Embeddings: {embed_result.embedded}")
    print(f"     • FAISS vectors: {vector_store.stats().total_vectors}")
    print(f"     • نموذج: sentence-transformers/all-MiniLM-L6-v2 ({dim} بُعد)")
    print(f"     • RAG pipeline: جاهز للـ LLM ✓")
    print("═" * 65)


if __name__ == "__main__":
    asyncio.run(run_demo())
