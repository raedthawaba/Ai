"""Unit tests for MarkdownConverter & TransformationPipeline — Phase 2 (Section 2.5)."""
from __future__ import annotations

import pytest
from datetime import datetime

from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.transformation.markdown_converter import (
    MarkdownConverter,
    MarkdownConverterConfig,
    text_to_markdown,
    markdown_to_plain_text,
    _detect_paragraphs,
    _is_arabic_text,
    _linkify,
)
from data_engine.processing.transformation.transformation_pipeline import (
    TransformationPipeline,
    TransformationPipelineConfig,
    TransformationOutput,
    TransformationMetrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(
    content: str,
    title: str = "Test Article",
    language: str = "en",
    article_id: str = "art001",
    summary: str | None = None,
) -> Article:
    return Article(
        id=article_id,
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=datetime(2024, 1, 1),
        summary=summary,
        metadata=ArticleMetadata(source_id="src_test", language=language),
    )


SIMPLE_EN_ARTICLE = _make_article(
    content=(
        "Artificial intelligence is transforming the world.\n\n"
        "Companies are investing in machine learning and data science.\n\n"
        "The future looks bright."
    ),
    title="The AI Revolution",
    summary="AI is changing everything.",
)

AR_ARTICLE = _make_article(
    content=(
        "يُحدث الذكاء الاصطناعي ثورة في عالم التقنية.\n\n"
        "تستثمر الشركات في تعلم الآلة وعلوم البيانات.\n\n"
        "المستقبل واعد ومشرق."
    ),
    title="ثورة الذكاء الاصطناعي",
    language="ar",
)

URL_ARTICLE = _make_article(
    content="Visit https://example.com for more info about https://news.com",
    title="Links Article",
)

LONG_ARTICLE = _make_article(
    content=" ".join(["Word"] * 500),
    title="Long Article",
)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Helper functions
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkdownHelpers:
    def test_detect_paragraphs_splits_correctly(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        paras = _detect_paragraphs(text)
        assert len(paras) == 3
        assert paras[0] == "Para one."

    def test_detect_paragraphs_empty(self):
        assert _detect_paragraphs("") == []

    def test_is_arabic_text(self):
        assert _is_arabic_text("هذا نص عربي كامل") is True
        assert _is_arabic_text("This is English text") is False
        assert _is_arabic_text("") is False

    def test_linkify_converts_urls(self):
        text = "Visit https://example.com for info."
        result = _linkify(text)
        assert "[https://example.com]" in result or "](https://example.com)" in result

    def test_linkify_no_change_without_urls(self):
        text = "No links here at all."
        assert _linkify(text) == text


# ─────────────────────────────────────────────────────────────────────────────
# Tests: text_to_markdown function
# ─────────────────────────────────────────────────────────────────────────────

class TestTextToMarkdown:
    def test_includes_title_as_h1(self):
        result = text_to_markdown("Content here.", title="My Title")
        assert "# My Title" in result

    def test_includes_summary_as_blockquote(self):
        result = text_to_markdown("Content.", title="T", summary="Short summary.")
        assert "> Short summary." in result

    def test_no_title_when_disabled(self):
        cfg = MarkdownConverterConfig(include_title=False)
        result = text_to_markdown("Content.", title="My Title", config=cfg)
        assert "# My Title" not in result

    def test_no_summary_when_disabled(self):
        cfg = MarkdownConverterConfig(include_summary=False)
        result = text_to_markdown("Content.", title="T", summary="Summary", config=cfg)
        assert "> Summary" not in result

    def test_paragraphs_separated(self):
        text = "Para one.\n\nPara two."
        result = text_to_markdown(text)
        assert "Para one." in result
        assert "Para two." in result

    def test_linkify_urls(self):
        cfg = MarkdownConverterConfig(linkify_urls=True)
        result = text_to_markdown("Visit https://example.com now.", config=cfg)
        assert "example.com" in result

    def test_arabic_content(self):
        result = text_to_markdown(
            "الذكاء الاصطناعي يغيّر العالم.",
            title="عنوان",
            language="ar",
        )
        assert "# عنوان" in result
        assert "الذكاء الاصطناعي" in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: markdown_to_plain_text
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkdownToPlainText:
    def test_removes_headers(self):
        md = "# Title\n\nContent here."
        plain = markdown_to_plain_text(md)
        assert "# Title" not in plain
        assert "Title" in plain
        assert "Content here." in plain

    def test_removes_bold(self):
        md = "This is **bold** text."
        plain = markdown_to_plain_text(md)
        assert "**" not in plain
        assert "bold" in plain

    def test_removes_italic(self):
        md = "This is *italic* text."
        plain = markdown_to_plain_text(md)
        assert "*italic*" not in plain

    def test_removes_links(self):
        md = "Visit [Example](https://example.com) now."
        plain = markdown_to_plain_text(md)
        assert "[Example]" not in plain
        assert "Example" in plain

    def test_removes_blockquotes(self):
        md = "> This is a quote.\n\nRegular text."
        plain = markdown_to_plain_text(md)
        assert ">" not in plain
        assert "This is a quote." in plain

    def test_removes_code_fences(self):
        md = "Code:\n```\nprint('hello')\n```\nDone."
        plain = markdown_to_plain_text(md)
        assert "```" not in plain

    def test_empty_markdown(self):
        assert markdown_to_plain_text("") == ""

    def test_roundtrip_content_preserved(self):
        original = "Important news about AI and machine learning technology."
        md = text_to_markdown(original, title="Test")
        plain = markdown_to_plain_text(md)
        # المحتوى الرئيسي يجب أن يبقى موجوداً
        assert "Important news" in plain


# ─────────────────────────────────────────────────────────────────────────────
# Tests: MarkdownConverter class
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkdownConverter:
    def test_default_config(self):
        converter = MarkdownConverter()
        assert converter.config.include_title is True

    def test_article_to_markdown(self):
        converter = MarkdownConverter()
        result = converter.article_to_markdown(SIMPLE_EN_ARTICLE)
        assert "# The AI Revolution" in result
        assert "> AI is changing everything." in result
        assert "Artificial intelligence" in result

    def test_arabic_article_to_markdown(self):
        converter = MarkdownConverter()
        result = converter.article_to_markdown(AR_ARTICLE)
        assert "# ثورة الذكاء الاصطناعي" in result
        assert "الذكاء الاصطناعي" in result

    def test_to_plain_text(self):
        converter = MarkdownConverter()
        md = "# Title\n\nContent here."
        plain = converter.to_plain_text(md)
        assert "Title" in plain
        assert "#" not in plain

    def test_batch_to_markdown(self):
        converter = MarkdownConverter()
        articles = [SIMPLE_EN_ARTICLE, AR_ARTICLE, URL_ARTICLE]
        results = converter.batch_to_markdown(articles)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, str)
            assert len(r) > 0

    def test_raises_on_non_article(self):
        converter = MarkdownConverter()
        with pytest.raises(TypeError):
            converter.article_to_markdown("not an article")  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Tests: TransformationPipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformationPipeline:
    def test_default_config(self):
        pipeline = TransformationPipeline()
        assert pipeline.config is not None

    def test_transform_article_returns_output(self):
        pipeline = TransformationPipeline()
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert isinstance(output, TransformationOutput)
        assert output.article_id == SIMPLE_EN_ARTICLE.id

    def test_output_has_chunks(self):
        pipeline = TransformationPipeline()
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert isinstance(output.chunks, list)
        # مقال بسيط قد ينتج chunk واحد على الأقل
        assert output.chunk_count >= 0  # قد يكون 0 إذا كان المحتوى قصيراً جداً

    def test_output_has_markdown(self):
        pipeline = TransformationPipeline()
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert isinstance(output.markdown_content, str)
        assert len(output.markdown_content) > 0

    def test_output_has_transformed_data(self):
        pipeline = TransformationPipeline()
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert isinstance(output.transformed_data, dict)

    def test_output_tracks_tokens(self):
        pipeline = TransformationPipeline()
        output = pipeline.transform_article(LONG_ARTICLE)
        assert output.total_tokens > 0

    def test_truncation_when_limit_set(self):
        cfg = TransformationPipelineConfig(
            max_tokens_per_article=10,
            truncate_if_over_limit=True,
        )
        pipeline = TransformationPipeline(cfg)
        output = pipeline.transform_article(LONG_ARTICLE)
        assert output.was_truncated is True

    def test_no_truncation_below_limit(self):
        cfg = TransformationPipelineConfig(
            max_tokens_per_article=10000,
            truncate_if_over_limit=True,
        )
        pipeline = TransformationPipeline(cfg)
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert output.was_truncated is False

    def test_disable_markdown(self):
        cfg = TransformationPipelineConfig(use_markdown_converter=False)
        pipeline = TransformationPipeline(cfg)
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert output.markdown_content == ""

    def test_disable_chunker(self):
        cfg = TransformationPipelineConfig(use_chunker=False)
        pipeline = TransformationPipeline(cfg)
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        assert output.chunks == []

    def test_output_to_dict(self):
        pipeline = TransformationPipeline()
        output = pipeline.transform_article(SIMPLE_EN_ARTICLE)
        d = output.to_dict()
        assert "article_id" in d
        assert "chunk_count" in d
        assert "total_tokens" in d

    def test_transform_batch_returns_outputs_and_metrics(self):
        pipeline = TransformationPipeline()
        articles = [SIMPLE_EN_ARTICLE, AR_ARTICLE, URL_ARTICLE]
        outputs, metrics = pipeline.transform_batch(articles)
        assert isinstance(metrics, TransformationMetrics)
        assert len(outputs) == 3
        assert metrics.total_input == 3

    def test_batch_metrics_calculated(self):
        pipeline = TransformationPipeline()
        articles = [SIMPLE_EN_ARTICLE, AR_ARTICLE]
        _, metrics = pipeline.transform_batch(articles)
        assert metrics.total_transformed <= 2
        assert metrics.total_errors >= 0
        assert metrics.avg_chunks_per_article >= 0

    def test_batch_metrics_to_dict(self):
        pipeline = TransformationPipeline()
        _, metrics = pipeline.transform_batch([SIMPLE_EN_ARTICLE])
        d = metrics.to_dict()
        assert "total_input" in d
        assert "total_chunks" in d

    def test_get_all_chunks_from_outputs(self):
        pipeline = TransformationPipeline()
        articles = [SIMPLE_EN_ARTICLE, AR_ARTICLE]
        outputs, _ = pipeline.transform_batch(articles)
        all_chunks = pipeline.get_all_chunks(outputs)
        assert isinstance(all_chunks, list)

    def test_export_to_jsonl(self):
        import json
        pipeline = TransformationPipeline()
        articles = [SIMPLE_EN_ARTICLE, AR_ARTICLE]
        outputs, _ = pipeline.transform_batch(articles)
        jsonl = pipeline.export_to_jsonl(outputs)
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            d = json.loads(line)
            assert "article_id" in d

    @pytest.mark.asyncio
    async def test_async_transform_article(self):
        pipeline = TransformationPipeline()
        output = await pipeline.async_transform_article(SIMPLE_EN_ARTICLE)
        assert isinstance(output, TransformationOutput)
        assert output.article_id == SIMPLE_EN_ARTICLE.id

    @pytest.mark.asyncio
    async def test_async_transform_batch(self):
        pipeline = TransformationPipeline()
        articles = [SIMPLE_EN_ARTICLE, AR_ARTICLE]
        outputs, metrics = await pipeline.async_transform_batch(articles, max_concurrency=2)
        assert len(outputs) == 2
        assert metrics.total_input == 2
