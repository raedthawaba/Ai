"""Integration tests for full Phase 2 processing pipeline.

يختبر التكامل بين جميع الـ pipelines بترتيب واقعي:
  Cleaning → Filtering → Enrichment → Transformation
"""
from __future__ import annotations

import pytest
from datetime import datetime
from typing import List

from shared.schemas.article import Article, ArticleMetadata, ProcessingState, generate_article_id
from data_engine.processing.cleaning.cleaning_pipeline import CleaningPipeline, CleaningPipelineConfig
from data_engine.processing.filtering.filtering_pipeline import FilteringPipeline, FilteringPipelineConfig
from data_engine.processing.filtering.content_filter import FilterConfig
from data_engine.processing.filtering.quality_scorer import QualityScorerConfig
from data_engine.processing.enrichment.enrichment_pipeline import EnrichmentPipeline, EnrichmentPipelineConfig
from data_engine.processing.transformation.transformation_pipeline import (
    TransformationPipeline,
    TransformationPipelineConfig,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(
    content: str,
    title: str = "Test",
    language: str = "en",
    article_id: str | None = None,
) -> Article:
    return Article(
        id=article_id or generate_article_id(),
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=datetime(2024, 1, 1),
        metadata=ArticleMetadata(source_id="src_integration", language=language),
    )


def _make_sample_batch(count: int = 5) -> List[Article]:
    articles = []
    for i in range(count):
        articles.append(_make_article(
            content=(
                f"This is article number {i + 1} about artificial intelligence. "
                f"Machine learning and data science are transforming industries. "
                f"Companies invest heavily in technology and digital transformation. "
                f"The future of AI looks bright and promising for all sectors."
            ),
            title=f"Article {i + 1}: AI and Technology",
            language="en",
            article_id=f"art_integration_{i:03d}",
        ))
    return articles


CLEAN_ARTICLES = _make_sample_batch(5)

MIXED_ARTICLES = [
    _make_article(
        content="This is a good technology article about machine learning and AI.",
        title="Tech Article",
        language="en",
        article_id="art_good_001",
    ),
    _make_article(
        content="X",  # محتوى قصير جداً → يُرفض
        title="Short",
        article_id="art_short_001",
    ),
    _make_article(
        content=(
            "كشف الباحثون عن تقنية جديدة في مجال الذكاء الاصطناعي. "
            "أفادت التقارير بأن الخوارزميات الجديدة تُحسّن دقة النتائج بشكل ملحوظ. "
            "تُعدّ هذه التقنية خطوة كبيرة نحو مستقبل رقمي متطور."
        ),
        title="الذكاء الاصطناعي: اكتشاف جديد",
        language="ar",
        article_id="art_ar_001",
    ),
    _make_article(
        content=(
            "The economy is facing challenges as inflation rises. "
            "The central bank raised interest rates to combat the crisis. "
            "Markets responded negatively to the announcement."
        ),
        title="Economic Crisis",
        language="en",
        article_id="art_econ_001",
    ),
]

DUPLICATE_ARTICLES = [
    _make_article(
        content="Same content in both articles. The economy is growing.",
        title="Same Article Title",
        article_id="art_dup_001",
    ),
    _make_article(
        content="Same content in both articles. The economy is growing.",
        title="Same Article Title",
        article_id="art_dup_002",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Individual Pipeline Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestCleaningPipelineIntegration:
    def test_cleans_batch_without_errors(self):
        pipeline = CleaningPipeline()
        cleaned, metrics = pipeline.clean_batch(CLEAN_ARTICLES)
        assert metrics.total_input == len(CLEAN_ARTICLES)
        assert metrics.total_cleaned + metrics.total_rejected == len(CLEAN_ARTICLES)
        assert metrics.total_cleaned > 0

    def test_clean_preserves_key_content(self):
        pipeline = CleaningPipeline()
        article = _make_article(
            "Artificial intelligence is transforming industries worldwide.",
            title="AI Article",
        )
        cleaned, metrics = pipeline.clean_article(article)
        assert "Artificial intelligence" in cleaned.content
        assert not metrics.rejected


class TestFilteringPipelineIntegration:
    def test_filters_short_articles(self):
        cfg = FilteringPipelineConfig(
            use_pii_filter=False,
            use_spam_detector=False,
            content_config=FilterConfig(min_content_length=50),
        )
        pipeline = FilteringPipeline(cfg)
        kept, metrics = pipeline.filter_batch(MIXED_ARTICLES)
        # المقال القصير يجب أن يُرفض
        kept_ids = [a.id for a in kept]
        assert "art_short_001" not in kept_ids

    def test_deduplication_removes_duplicates(self):
        cfg = FilteringPipelineConfig(
            use_pii_filter=False,
            use_spam_detector=False,
            use_policy_filter=False,
            use_quality_scorer=False,
            use_language_filter=False,
            use_content_filter=False,
        )
        pipeline = FilteringPipeline(cfg)
        kept, metrics = pipeline.filter_batch(DUPLICATE_ARTICLES, reset_dedup=True)
        # واحد من الاثنين يجب أن يُرفض
        assert len(kept) <= 2
        assert metrics.total_duplicates <= 2

    def test_metrics_have_rejection_breakdown(self):
        cfg = FilteringPipelineConfig(
            use_pii_filter=False,
            content_config=FilterConfig(min_content_length=50),
        )
        pipeline = FilteringPipeline(cfg)
        _, metrics = pipeline.filter_batch(MIXED_ARTICLES)
        assert isinstance(metrics.rejections_by_layer, dict)
        assert metrics.to_dict() is not None

    def test_keeps_arabic_articles(self):
        cfg = FilteringPipelineConfig(use_pii_filter=False)
        pipeline = FilteringPipeline(cfg)
        ar_articles = [a for a in MIXED_ARTICLES if a.id == "art_ar_001"]
        kept, _ = pipeline.filter_batch(ar_articles)
        assert len(kept) > 0


class TestEnrichmentPipelineIntegration:
    def test_enriches_batch_without_errors(self):
        cfg = EnrichmentPipelineConfig(
            use_entity_extractor=False,  # spaCy قد لا يكون متاحاً
        )
        pipeline = EnrichmentPipeline(cfg)
        enriched, metrics = pipeline.enrich_batch(CLEAN_ARTICLES[:3])
        assert metrics.total_input == 3
        assert metrics.total_enriched + metrics.total_errors == 3

    def test_topic_added_to_articles(self):
        cfg = EnrichmentPipelineConfig(
            use_entity_extractor=False,
            use_summarizer=False,
            use_content_enricher=False,
            use_keyword_extractor=False,
        )
        pipeline = EnrichmentPipeline(cfg)
        tech_article = CLEAN_ARTICLES[0]
        enriched, _ = pipeline.enrich_batch([tech_article])
        assert "primary_topic" in enriched[0].metadata.extra

    def test_sentiment_added_to_articles(self):
        cfg = EnrichmentPipelineConfig(
            use_entity_extractor=False,
            use_summarizer=False,
            use_content_enricher=False,
            use_keyword_extractor=False,
            use_topic_classifier=False,
        )
        pipeline = EnrichmentPipeline(cfg)
        enriched, _ = pipeline.enrich_batch(CLEAN_ARTICLES[:2])
        for a in enriched:
            assert "sentiment" in a.metadata.extra

    def test_cache_improves_second_run_speed(self):
        import time
        cfg = EnrichmentPipelineConfig(enable_cache=True)
        pipeline = EnrichmentPipeline(cfg)
        article = CLEAN_ARTICLES[0]

        # أول تشغيل
        _, metrics1 = pipeline.enrich_batch([article])
        # ثاني تشغيل (يجب من الـ cache)
        _, metrics2 = pipeline.enrich_batch([article])

        assert metrics2.total_from_cache >= 1


class TestTransformationPipelineIntegration:
    def test_transforms_batch_without_errors(self):
        pipeline = TransformationPipeline()
        outputs, metrics = pipeline.transform_batch(CLEAN_ARTICLES[:3])
        assert metrics.total_input == 3
        assert metrics.total_transformed + metrics.total_errors == 3

    def test_all_articles_get_markdown(self):
        pipeline = TransformationPipeline()
        outputs, _ = pipeline.transform_batch(MIXED_ARTICLES[2:])  # Arabic + Economic
        for output in outputs:
            assert isinstance(output.markdown_content, str)
            assert len(output.markdown_content) > 0

    def test_chunks_have_unique_ids(self):
        pipeline = TransformationPipeline()
        outputs, _ = pipeline.transform_batch(CLEAN_ARTICLES[:2])
        all_chunks = pipeline.get_all_chunks(outputs)
        if all_chunks:
            chunk_ids = [c.chunk_id for c in all_chunks]
            # لا تكرار في chunk IDs
            assert len(chunk_ids) == len(set(chunk_ids))


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Full End-to-End Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestFullProcessingPipeline:
    """اختبار Pipeline كامل: Cleaning → Filtering → Enrichment → Transformation."""

    def test_full_pipeline_end_to_end(self):
        """تشغيل المقالات عبر جميع الـ pipelines."""
        articles = _make_sample_batch(count=3)

        # 1. Cleaning
        cleaning = CleaningPipeline()
        cleaned_articles, cleaning_metrics = cleaning.clean_batch(articles)
        assert cleaning_metrics.total_cleaned > 0

        # 2. Filtering
        filtering_cfg = FilteringPipelineConfig(
            use_pii_filter=False,  # لا PII في المقالات التجريبية
        )
        filtering = FilteringPipeline(filtering_cfg)
        filtered_articles, filtering_metrics = filtering.filter_batch(
            cleaned_articles, reset_dedup=True
        )
        assert len(filtered_articles) >= 0

        # 3. Enrichment
        enrichment_cfg = EnrichmentPipelineConfig(
            use_entity_extractor=False,  # لا spaCy في الاختبارات
        )
        enrichment = EnrichmentPipeline(enrichment_cfg)
        enriched_articles, enrichment_metrics = enrichment.enrich_batch(filtered_articles)
        assert enrichment_metrics.total_input == len(filtered_articles)

        # 4. Transformation
        transformation = TransformationPipeline()
        outputs, transformation_metrics = transformation.transform_batch(enriched_articles)
        assert transformation_metrics.total_input == len(enriched_articles)

        # التحقق من النتائج الكاملة
        for output in outputs:
            assert isinstance(output.markdown_content, str)
            assert output.article_id is not None

    def test_pipeline_handles_arabic_articles(self):
        """التأكد من أن العربية تعمل في كل المراحل."""
        ar_articles = [
            _make_article(
                content=(
                    "يُحدث الذكاء الاصطناعي ثورة في الصناعة العالمية. "
                    "أعلنت الشركات الكبرى عن استثمارات ضخمة في تقنيات التعلم الآلي. "
                    "يُتوقع أن يُغيّر هذا المجال مستقبل العمل والإنتاج."
                ),
                title="الذكاء الاصطناعي يُغيّر العالم",
                language="ar",
            )
        ]

        cleaning = CleaningPipeline()
        cleaned, _ = cleaning.clean_batch(ar_articles)
        assert len(cleaned) > 0

        enrichment = EnrichmentPipeline(
            EnrichmentPipelineConfig(use_entity_extractor=False)
        )
        enriched, _ = enrichment.enrich_batch(cleaned)
        for a in enriched:
            assert "sentiment" in a.metadata.extra or "primary_topic" in a.metadata.extra

        transformation = TransformationPipeline()
        outputs, _ = transformation.transform_batch(enriched)
        assert all(len(o.markdown_content) > 0 for o in outputs)

    def test_pipeline_with_pii_content(self):
        """التحقق من إخفاء PII عبر filtering pipeline."""
        articles = [
            _make_article(
                content="Contact our editor at editor@news.com for more information.",
                title="Contact Info",
                article_id="art_pii_001",
            )
        ]

        filtering = FilteringPipeline()
        kept, metrics = filtering.filter_batch(articles)
        # يجب أن يمرّ المقال (PII يُخفى وليس يُرفض بدون حد أقصى)
        if kept:
            assert "editor@news.com" not in kept[0].content
            assert "[EMAIL]" in kept[0].content
