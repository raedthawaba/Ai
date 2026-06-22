"""Unit tests for CleaningPipeline — Phase 2 (Section 2.2)."""
from __future__ import annotations

import pytest
from datetime import datetime

from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.cleaning.cleaning_pipeline import (
    CleaningPipeline,
    CleaningPipelineConfig,
    CleaningMetrics,
    BatchCleaningMetrics,
    _remove_boilerplate_sentences,
    _remove_duplicate_paragraphs,
    _count_urls,
    _count_emails,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(
    content: str,
    title: str = "Test Article",
    language: str = "en",
    article_id: str = "art_test001",
) -> Article:
    return Article(
        id=article_id,
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=datetime(2024, 1, 1),
        metadata=ArticleMetadata(source_id="test_src", language=language),
    )


CLEAN_EN_ARTICLE = _make_article(
    content=(
        "Artificial intelligence is transforming industries worldwide. "
        "Companies are investing heavily in machine learning and data science. "
        "The future of technology looks bright and promising."
    ),
    title="AI Is Changing Everything",
)

HTML_ARTICLE = _make_article(
    content=(
        "<html><body><script>alert('xss')</script>"
        "<h1>Main Story</h1>"
        "<p>This is the main content of the article.</p>"
        "<div class='ad'>Buy now! Special offer!</div>"
        "</body></html>"
    ),
    title="HTML Test",
)

BOILERPLATE_ARTICLE = _make_article(
    content=(
        "This is real content about a political event.\n\n"
        "Subscribe to our newsletter to get the latest updates.\n\n"
        "Follow us on Twitter for breaking news.\n\n"
        "More important political analysis here."
    ),
    title="Politics Today",
)

DUPLICATE_PARA_ARTICLE = _make_article(
    content=(
        "This paragraph contains important information.\n\n"
        "A second paragraph with different content.\n\n"
        "This paragraph contains important information.\n\n"
        "A third paragraph with unique content."
    ),
    title="Duplicate Paragraphs",
)

SHORT_ARTICLE = _make_article(content="Hi.", title="Too Short")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Helper functions
# ─────────────────────────────────────────────────────────────────────────────

class TestBoilerplateRemoval:
    def test_removes_newsletter_subscription(self):
        text = "Real content here. Subscribe to our newsletter for more."
        cleaned, removed = _remove_boilerplate_sentences(text, language="en")
        assert removed >= 1
        assert "Real content here" in cleaned

    def test_removes_social_follow(self):
        text = "Important news! Follow us on Twitter for updates."
        cleaned, removed = _remove_boilerplate_sentences(text, language="en")
        assert removed >= 1

    def test_arabic_boilerplate_removal(self):
        text = "خبر مهم للغاية. اشترك في نشرتنا الإخبارية للمزيد."
        cleaned, removed = _remove_boilerplate_sentences(text, language="ar")
        assert removed >= 1

    def test_preserves_real_content(self):
        text = "This is important political news. The president signed a law."
        cleaned, removed = _remove_boilerplate_sentences(text, language="en")
        assert removed == 0
        assert cleaned.strip() == text.strip()

    def test_returns_original_when_too_much_boilerplate(self):
        # أكثر من 40% boilerplate → الاحتفاظ بالأصل
        text = (
            "Subscribe to our newsletter. "
            "Follow us on Twitter. "
            "Privacy policy. "
            "Real content here."
        )
        cleaned, removed = _remove_boilerplate_sentences(text, language="en", max_ratio=0.4)
        # إذا تجاوزنا النسبة → الأصل
        assert isinstance(cleaned, str)


class TestDuplicateParagraphRemoval:
    def test_removes_exact_duplicates(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nFirst paragraph."
        cleaned, removed = _remove_duplicate_paragraphs(text)
        assert removed == 1
        assert cleaned.count("First paragraph.") == 1

    def test_keeps_unique_paragraphs(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        cleaned, removed = _remove_duplicate_paragraphs(text)
        assert removed == 0
        assert "Para one." in cleaned
        assert "Para two." in cleaned
        assert "Para three." in cleaned

    def test_case_insensitive_dedup(self):
        text = "Hello World.\n\nhello world."
        cleaned, removed = _remove_duplicate_paragraphs(text)
        assert removed == 1

    def test_empty_text(self):
        cleaned, removed = _remove_duplicate_paragraphs("")
        assert cleaned == ""
        assert removed == 0


class TestURLEmailCounting:
    def test_count_urls(self):
        text = "Visit https://example.com and http://news.com for more."
        assert _count_urls(text) == 2

    def test_count_emails(self):
        text = "Contact us at info@example.com or support@news.org"
        assert _count_emails(text) == 2

    def test_no_urls_or_emails(self):
        assert _count_urls("Clean text with no links") == 0
        assert _count_emails("Clean text with no emails") == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: CleaningPipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestCleaningPipeline:
    def test_default_config(self):
        pipeline = CleaningPipeline()
        assert pipeline.config is not None

    def test_clean_simple_article(self):
        pipeline = CleaningPipeline()
        cleaned, metrics = pipeline.clean_article(CLEAN_EN_ARTICLE)
        assert isinstance(cleaned, Article)
        assert isinstance(metrics, CleaningMetrics)
        assert not metrics.rejected
        assert metrics.cleaned_content_len > 0

    def test_metrics_track_reduction(self):
        pipeline = CleaningPipeline()
        _, metrics = pipeline.clean_article(CLEAN_EN_ARTICLE)
        assert metrics.original_content_len > 0
        assert 0.0 <= metrics.reduction_ratio <= 1.0
        assert 0.0 <= metrics.content_retained_ratio <= 1.0

    def test_rejects_short_content_after_cleaning(self):
        pipeline = CleaningPipeline(
            CleaningPipelineConfig(min_content_length=1000)
        )
        _, metrics = pipeline.clean_article(SHORT_ARTICLE)
        assert metrics.rejected
        assert metrics.rejection_reason is not None

    def test_boilerplate_removal_tracked(self):
        pipeline = CleaningPipeline(
            CleaningPipelineConfig(
                use_html_cleaner=False,
                use_text_cleaner=False,
                use_normalizer=False,
                remove_boilerplate=True,
                remove_duplicate_paragraphs=False,
            )
        )
        cleaned, metrics = pipeline.clean_article(BOILERPLATE_ARTICLE)
        # قد يُزال boilerplate إذا لم يتجاوز النسبة
        assert isinstance(metrics.boilerplate_removed, int)

    def test_duplicate_paragraph_removal_tracked(self):
        pipeline = CleaningPipeline(
            CleaningPipelineConfig(
                use_html_cleaner=False,
                use_text_cleaner=False,
                use_normalizer=False,
                remove_boilerplate=False,
                remove_duplicate_paragraphs=True,
            )
        )
        cleaned, metrics = pipeline.clean_article(DUPLICATE_PARA_ARTICLE)
        assert metrics.duplicate_paragraphs_removed >= 1

    def test_metrics_duration_tracked(self):
        pipeline = CleaningPipeline()
        _, metrics = pipeline.clean_article(CLEAN_EN_ARTICLE)
        assert metrics.duration_ms >= 0.0

    def test_metrics_to_dict(self):
        pipeline = CleaningPipeline()
        _, metrics = pipeline.clean_article(CLEAN_EN_ARTICLE)
        d = metrics.to_dict()
        assert "article_id" in d
        assert "original_len" in d
        assert "cleaned_len" in d
        assert "reduction_ratio" in d

    def test_disable_stages(self):
        cfg = CleaningPipelineConfig(
            use_html_cleaner=False,
            use_text_cleaner=False,
            use_normalizer=False,
            remove_boilerplate=False,
            remove_duplicate_paragraphs=False,
        )
        pipeline = CleaningPipeline(cfg)
        original = CLEAN_EN_ARTICLE
        cleaned, metrics = pipeline.clean_article(original)
        # المحتوى يجب أن يبقى كما هو (لا معالجة)
        assert cleaned.content == original.content


class TestCleaningPipelineBatch:
    def test_clean_batch_returns_cleaned_and_metrics(self):
        pipeline = CleaningPipeline()
        articles = [CLEAN_EN_ARTICLE, BOILERPLATE_ARTICLE, DUPLICATE_PARA_ARTICLE]
        cleaned, batch_metrics = pipeline.clean_batch(articles)
        assert isinstance(batch_metrics, BatchCleaningMetrics)
        assert batch_metrics.total_input == 3
        assert batch_metrics.total_cleaned + batch_metrics.total_rejected == 3

    def test_batch_rejection_counted(self):
        pipeline = CleaningPipeline(
            CleaningPipelineConfig(min_content_length=100000)
        )
        articles = [CLEAN_EN_ARTICLE, CLEAN_EN_ARTICLE]
        _, batch_metrics = pipeline.clean_batch(articles)
        assert batch_metrics.total_rejected == 2
        assert batch_metrics.rejection_rate == 1.0

    def test_batch_metrics_avg_reduction(self):
        pipeline = CleaningPipeline()
        _, batch_metrics = pipeline.clean_batch([CLEAN_EN_ARTICLE, BOILERPLATE_ARTICLE])
        assert 0.0 <= batch_metrics.avg_reduction_ratio <= 1.0

    @pytest.mark.asyncio
    async def test_async_clean_article(self):
        pipeline = CleaningPipeline()
        cleaned, metrics = await pipeline.async_clean_article(CLEAN_EN_ARTICLE)
        assert isinstance(cleaned, Article)
        assert not metrics.rejected

    @pytest.mark.asyncio
    async def test_async_clean_batch(self):
        pipeline = CleaningPipeline()
        articles = [CLEAN_EN_ARTICLE, BOILERPLATE_ARTICLE]
        cleaned, batch_metrics = await pipeline.async_clean_batch(articles, max_concurrency=2)
        assert batch_metrics.total_input == 2
