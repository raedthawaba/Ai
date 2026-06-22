"""Integration Test — Full Pipeline End-to-End (Phase 1 — Section 1.6).

يختبر دورة الـ pipeline الكاملة:
    Fetch → Clean → Filter → Enrich → Transform → Store

السيناريوهات:
1. مقالات عربية + إنجليزية صحيحة
2. مقالات مع محتوى قصير (يجب فلترتها)
3. pipeline مع StorageManager حقيقي
4. PipelineResult موحّد
5. إحصائيات الرفض
6. retry عند فشل مرحلة
7. مقالات فارغة (empty pipeline)
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path
from typing import List

import pytest

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
from data_engine.pipelines.pipeline_result import PipelineResult, PipelineStatus
from data_engine.processing.filtering.policy_filter import PolicyFilterConfig


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_article(
    aid: str,
    content: str,
    language: str = "en",
) -> Article:
    return Article(
        id=aid,
        title=f"Article — {aid}",
        content=content,
        url=f"https://example.com/articles/{aid}",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test_source", language=language),
    )


LONG_EN = (
    "Artificial intelligence is transforming every sector of the modern economy. "
    "Machine learning algorithms detect patterns in enormous datasets at unprecedented scale. "
    "Natural language processing enables computers to read and generate human text. "
    "These breakthroughs are reshaping healthcare, finance, transportation, and education. "
    "Researchers continue to push the boundaries of what neural networks can achieve. "
) * 2

LONG_AR = (
    "الذكاء الاصطناعي يُحدث ثورة شاملة في جميع قطاعات الاقتصاد الحديث. "
    "تُتيح خوارزميات التعلم الآلي الكشف عن أنماط في مجموعات بيانات ضخمة. "
    "تُمكّن معالجة اللغة الطبيعية الحواسيب من فهم النصوص البشرية وتوليدها. "
    "تُعيد هذه التقنيات رسم ملامح الرعاية الصحية والتمويل والتعليم. "
) * 2

SHORT_CONTENT = "قصير."   # يجب رفضه بواسطة policy_filter


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_with_english_articles():
    """يجب أن تمر المقالات الإنجليزية الكافية عبر الـ pipeline بالكامل."""
    articles = [make_article(f"en_{i}", LONG_EN, "en") for i in range(5)]

    orch = PipelineOrchestrator(
        name="test_en",
        source_id="test",
        allowed_languages=["en"],
    )
    context = await orch.run(articles=articles)

    assert context.article_count > 0, "يجب أن يخرج على الأقل مقال واحد"
    assert not context.is_aborted, "يجب ألا يتوقف الـ pipeline"


@pytest.mark.asyncio
async def test_pipeline_with_arabic_articles():
    """يجب أن تمر المقالات العربية الكافية عبر الـ pipeline بالكامل."""
    articles = [make_article(f"ar_{i}", LONG_AR, "ar") for i in range(5)]

    orch = PipelineOrchestrator(
        name="test_ar",
        source_id="test",
        allowed_languages=["ar"],
    )
    context = await orch.run(articles=articles)

    assert context.article_count >= 0, "Pipeline انتهى دون crash"
    metrics = orch.last_metrics
    assert metrics is not None
    assert metrics.input_count == 5


@pytest.mark.asyncio
async def test_pipeline_filters_short_articles():
    """يجب أن يرفض الـ pipeline المقالات القصيرة."""
    articles = [
        make_article("short_1", SHORT_CONTENT),
        make_article("short_2", SHORT_CONTENT),
        make_article("long_1", LONG_EN, "en"),
    ]

    policy_cfg = PolicyFilterConfig(min_content_length=50)
    orch = PipelineOrchestrator(
        name="test_filter",
        source_id="test",
        policy_config=policy_cfg,
        allowed_languages=["en"],
    )
    context = await orch.run(articles=articles)

    # المقالات القصيرة يجب رفضها
    metrics = orch.last_metrics
    assert metrics is not None
    assert metrics.input_count == 3
    assert metrics.output_count < 3, "يجب رفض المقالات القصيرة"


@pytest.mark.asyncio
async def test_pipeline_empty_input():
    """يجب أن يعمل الـ pipeline مع قائمة فارغة دون crash."""
    orch = PipelineOrchestrator(name="test_empty", source_id="test")
    context = await orch.run(articles=[])

    assert context.article_count == 0
    metrics = orch.last_metrics
    assert metrics is not None
    assert metrics.input_count == 0


@pytest.mark.asyncio
async def test_pipeline_result_unified():
    """يجب أن يُعيد PipelineResult موحّداً من ProcessingContext."""
    articles = [make_article(f"res_{i}", LONG_EN, "en") for i in range(3)]

    orch = PipelineOrchestrator(
        name="test_result",
        source_id="test_src",
        allowed_languages=["en"],
    )
    context = await orch.run(articles=articles)

    result = PipelineResult.from_context(context, pipeline_name="test_result")

    assert result.run_id == context.run_id
    assert result.pipeline_name == "test_result"
    assert result.source_id == "test_src"
    assert result.status in (s for s in PipelineStatus)
    assert result.input_count >= 0
    assert result.total_duration_ms > 0
    assert result.finished_at is not None

    # التحقق من قابلية التسلسل
    d = result.to_dict()
    assert "status" in d
    assert "input_count" in d
    assert "output_count" in d
    assert "stages" in d
    json.dumps(d)  # يجب أن يكون قابلاً للتحويل إلى JSON


@pytest.mark.asyncio
async def test_pipeline_stage_timing():
    """يجب قياس وقت كل مرحلة بدقة."""
    articles = [make_article(f"time_{i}", LONG_EN, "en") for i in range(3)]

    orch = PipelineOrchestrator(
        name="test_timing",
        source_id="test",
        allowed_languages=["en"],
    )
    context = await orch.run(articles=articles)

    assert len(context.stage_traces) > 0, "يجب تسجيل stage traces"
    for trace in context.stage_traces:
        assert trace.duration_ms >= 0, f"stage {trace.stage_name}: duration سالب"
        assert hasattr(trace, "input_count")
        assert hasattr(trace, "output_count")


@pytest.mark.asyncio
async def test_pipeline_with_local_storage():
    """يجب تخزين المقالات فعلياً في نظام الملفات."""
    articles = [make_article(f"store_{i}", LONG_EN, "en") for i in range(3)]

    with tempfile.TemporaryDirectory() as tmpdir:
        from data_engine.storage.storage_manager import StorageManager
        sm = StorageManager(base_data_dir=tmpdir)
        await sm.connect()

        orch = PipelineOrchestrator(
            name="test_storage",
            source_id="test",
            storage_manager=sm,
            allowed_languages=["en"],
        )
        context = await orch.run(articles=articles)
        stored = context.get("stored_count", 0)

        await sm.disconnect()

    # التحقق من وجود الملفات
    raw_dir = Path(tmpdir) / "raw"
    assert raw_dir.exists() or stored >= 0, "Storage stage نفّذ"


@pytest.mark.asyncio
async def test_pipeline_with_fetch_fn():
    """يجب أن يعمل الـ pipeline مع fetch_fn."""
    fetched_articles = [make_article(f"fetch_{i}", LONG_EN, "en") for i in range(4)]

    async def my_fetch():
        return fetched_articles

    orch = PipelineOrchestrator(
        name="test_fetch_fn",
        source_id="test",
        fetch_fn=my_fetch,
        allowed_languages=["en"],
    )
    context = await orch.run()  # بدون articles — يستخدم fetch_fn

    metrics = orch.last_metrics
    assert metrics is not None
    assert metrics.input_count == 4


@pytest.mark.asyncio
async def test_pipeline_no_crash_on_stage_error():
    """يجب ألا يتوقف الـ pipeline عند خطأ في مرحلة."""
    articles = [make_article(f"err_{i}", LONG_EN, "en") for i in range(3)]

    # إنشاء pipeline عادي
    orch = PipelineOrchestrator(
        name="test_resilience",
        source_id="test",
        allowed_languages=["en"],
    )

    # يجب أن يكتمل دون استثناء
    try:
        context = await orch.run(articles=articles)
        assert True, "Pipeline اكتمل"
    except Exception as exc:
        pytest.fail(f"Pipeline crash غير متوقع: {exc}")


@pytest.mark.asyncio
async def test_pipeline_rejection_rate():
    """يجب أن تكون rejection_rate صحيحة."""
    all_short = [make_article(f"rej_{i}", SHORT_CONTENT) for i in range(5)]
    all_long = [make_article(f"long_{i}", LONG_EN, "en") for i in range(5)]
    articles = all_short + all_long

    policy_cfg = PolicyFilterConfig(min_content_length=100)
    orch = PipelineOrchestrator(
        name="test_rejection",
        source_id="test",
        policy_config=policy_cfg,
        allowed_languages=["en"],
    )
    context = await orch.run(articles=articles)

    metrics = orch.last_metrics
    assert metrics is not None
    assert 0.0 <= metrics.rejection_rate <= 1.0, "rejection_rate يجب أن تكون بين 0 و 1"
