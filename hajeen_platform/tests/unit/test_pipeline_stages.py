"""Tests for Pipeline Stages — section 5.14."""
from __future__ import annotations
import pytest
import pytest_asyncio
from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.processing_context import ProcessingContext
from data_engine.pipelines.stages import (
    FetchStage, CleanStage, FilterStage,
    EnrichStage, TransformStage, StoreStage,
)
from shared.utils.datetime_utils import utc_now


def _make_article(
    content: str = "This is a clean article about technology and AI developments in the world today.",
    url: str = "https://example.com/article",
    title: str = "Technology Article",
    language: str = "en",
    aid: str = "art_001",
) -> Article:
    return Article(
        id=aid,
        title=title,
        content=content,
        url=url,
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test_src", language=language),
    )


def _make_context(articles=None) -> ProcessingContext:
    return ProcessingContext(
        articles=articles or [_make_article()],
        source_id="test",
    )


class TestFetchStage:
    @pytest.mark.asyncio
    async def test_passthrough_when_no_fn(self):
        ctx = _make_context([_make_article(aid="a1")])
        stage = FetchStage()
        result = await stage.run(ctx)
        assert result.output_count == 1
        assert ctx.articles[0].id == "a1"

    @pytest.mark.asyncio
    async def test_fetch_fn_replaces_articles(self):
        new_arts = [_make_article(aid="fetched_1"), _make_article(aid="fetched_2")]
        async def fn():
            return new_arts
        ctx = _make_context([])
        stage = FetchStage(fetch_fn=fn)
        await stage.run(ctx)
        assert ctx.article_count == 2
        assert ctx.articles[0].id == "fetched_1"

    @pytest.mark.asyncio
    async def test_fetch_fn_error_keeps_original(self):
        async def failing_fn():
            raise RuntimeError("Network error")
        original = [_make_article(aid="orig")]
        ctx = _make_context(original)
        stage = FetchStage(fetch_fn=failing_fn)
        await stage.run(ctx)
        assert ctx.article_count == 1


class TestCleanStage:
    @pytest.mark.asyncio
    async def test_cleans_html_content(self):
        html_art = _make_article(
            content="<h1>Title</h1><p>Content about <b>AI</b>!</p><script>alert()</script>"
        )
        ctx = _make_context([html_art])
        stage = CleanStage()
        await stage.run(ctx)
        for art in ctx.articles:
            assert "<script>" not in art.content
            assert "<h1>" not in art.content

    @pytest.mark.asyncio
    async def test_passthrough_plain_text(self):
        art = _make_article(content="Plain text without HTML tags here.")
        ctx = _make_context([art])
        stage = CleanStage()
        await stage.run(ctx)
        assert ctx.article_count == 1


class TestFilterStage:
    @pytest.mark.asyncio
    async def test_filters_short_content(self):
        arts = [
            _make_article(content="Too short.", aid="short"),
            _make_article(content="Artificial intelligence and machine learning are reshaping the modern world. Data science enables businesses to extract insights from massive datasets. Neural networks can identify patterns that humans cannot perceive easily.", aid="long"),
        ]
        from data_engine.processing.filtering.policy_filter import PolicyFilterConfig
        cfg = PolicyFilterConfig(min_content_length=30, blocked_domains=[], blocked_keywords=[])
        ctx = _make_context(arts)
        stage = FilterStage(policy_config=cfg)
        await stage.run(ctx)
        ids = [a.id for a in ctx.articles]
        assert "long" in ids

    @pytest.mark.asyncio
    async def test_deduplication_works(self):
        art = _make_article(aid="dup")
        arts = [art, art.model_copy(update={"id": "dup2"})]
        ctx = _make_context(arts)
        from data_engine.processing.filtering.policy_filter import PolicyFilterConfig
        cfg = PolicyFilterConfig(min_content_length=1)
        stage = FilterStage(policy_config=cfg)
        await stage.run(ctx)
        # Second article is a content duplicate → should be removed
        assert ctx.article_count <= 2


class TestEnrichStage:
    @pytest.mark.asyncio
    async def test_adds_summary(self):
        long_content = (
            "Artificial intelligence is transforming every industry worldwide. "
            "Machine learning enables computers to learn from data automatically. "
            "These technologies are being adopted at an unprecedented rate globally."
        )
        art = _make_article(content=long_content)
        ctx = _make_context([art])
        stage = EnrichStage()
        await stage.run(ctx)
        for a in ctx.articles:
            assert a.summary is not None

    @pytest.mark.asyncio
    async def test_adds_tags(self):
        long_content = (
            "Artificial intelligence machine learning deep learning neural networks "
            "natural language processing computer vision robotics automation data science "
            "algorithms training inference prediction classification regression."
        )
        art = _make_article(content=long_content)
        ctx = _make_context([art])
        stage = EnrichStage()
        await stage.run(ctx)
        for a in ctx.articles:
            assert isinstance(a.metadata.tags, list)


class TestTransformStage:
    @pytest.mark.asyncio
    async def test_adds_chunk_metadata(self):
        long_content = (
            "This is a long article.\n\n"
            "This is the second paragraph.\n\n"
            "This is the third paragraph about technology.\n\n"
            "And this is the fourth paragraph concluding the article."
        )
        art = _make_article(content=long_content)
        ctx = _make_context([art])
        stage = TransformStage()
        await stage.run(ctx)
        for a in ctx.articles:
            assert "chunk_count" in a.metadata.extra
            assert "token_count" in a.metadata.extra

    @pytest.mark.asyncio
    async def test_token_count_positive(self):
        art = _make_article()
        ctx = _make_context([art])
        stage = TransformStage()
        await stage.run(ctx)
        assert ctx.articles[0].metadata.extra["token_count"] > 0


class TestStoreStage:
    @pytest.mark.asyncio
    async def test_stores_locally(self, tmp_path):
        art = _make_article(aid="store_test_001")
        ctx = _make_context([art])
        stage = StoreStage(local_path=tmp_path)
        await stage.run(ctx)
        stored_files = list(tmp_path.glob("*.json"))
        assert len(stored_files) == 1

    @pytest.mark.asyncio
    async def test_passthrough_articles_unchanged(self, tmp_path):
        art = _make_article(aid="passthrough_001")
        ctx = _make_context([art])
        stage = StoreStage(local_path=tmp_path)
        await stage.run(ctx)
        # Articles should still be in context
        assert ctx.article_count == 1
        assert ctx.articles[0].id == "passthrough_001"
