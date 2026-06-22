"""Tests for section 5.1 — Processing Architecture."""

import pytest

from data_engine.processing import (
    BaseProcessor,
    ChainedProcessor,
    PassthroughProcessor,
    ProcessingContext,
    ProcessingError,
    ProcessingResult,
    StageTrace,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_articles(n: int = 3) -> list[Article]:
    return [
        Article(
            id=generate_article_id(f"Article {i}"),
            title=f"Article {i}",
            content=f"Content for article {i} with enough text.",
            url=f"https://example.com/a{i}",
            published_at=utc_now(),
            metadata=ArticleMetadata(source_id="test"),
        )
        for i in range(n)
    ]


class DoubleProcessor(BaseProcessor):
    """Duplicates the article list (for chaining tests)."""

    async def process_articles(self, articles, context):
        return articles + articles


class FilterEvenProcessor(BaseProcessor):
    """Keeps only articles at even indices."""

    async def process_articles(self, articles, context):
        return [a for i, a in enumerate(articles) if i % 2 == 0]


class BoomProcessor(BaseProcessor):
    """Always raises an exception."""

    async def process_articles(self, articles, context):
        raise RuntimeError("boom")


class MetadataProcessor(BaseProcessor):
    """Stores a value in context metadata."""

    async def process_articles(self, articles, context):
        context.set("processed_by", self.name)
        return articles


# ---------------------------------------------------------------------------
# ProcessingResult
# ---------------------------------------------------------------------------

class TestProcessingResult:
    def test_empty(self):
        r = ProcessingResult.empty("test_stage")
        assert r.stage_name == "test_stage"
        assert r.input_count == 0
        assert r.output_count == 0
        assert r.pass_rate == 1.0

    def test_from_articles(self):
        arts = make_articles(5)
        r = ProcessingResult.from_articles("stage", 5, arts[:3], duration_ms=10.0)
        assert r.input_count == 5
        assert r.output_count == 3
        assert r.rejected_count == 2
        assert r.duration_ms == 10.0

    def test_pass_rate(self):
        arts = make_articles(4)
        r = ProcessingResult.from_articles("s", 4, arts[:2])
        assert r.pass_rate == 0.5

    def test_pass_rate_zero_input(self):
        r = ProcessingResult.from_articles("s", 0, [])
        assert r.pass_rate == 1.0

    def test_add_error(self):
        r = ProcessingResult.empty("s")
        r.add_error("s", "oops", article_id="abc")
        assert r.error_count == 1
        assert r.errors[0].article_id == "abc"

    def test_summary_keys(self):
        arts = make_articles(2)
        r = ProcessingResult.from_articles("s", 2, arts)
        s = r.summary()
        assert set(s.keys()) >= {"stage", "input", "output", "rejected", "errors", "pass_rate", "success"}

    def test_success_property(self):
        arts = make_articles(2)
        r = ProcessingResult.from_articles("s", 2, arts)
        assert r.success is True

    def test_processing_error_str(self):
        e = ProcessingError(stage="clean", message="bad input", article_id="x1")
        assert "clean" in str(e)
        assert "x1" in str(e)


# ---------------------------------------------------------------------------
# ProcessingContext
# ---------------------------------------------------------------------------

class TestProcessingContext:
    def test_initial_state(self):
        arts = make_articles(3)
        ctx = ProcessingContext(articles=arts, source_id="src")
        assert ctx.article_count == 3
        assert ctx.source_id == "src"
        assert not ctx.has_errors
        assert not ctx.is_aborted

    def test_replace_articles(self):
        ctx = ProcessingContext(articles=make_articles(3))
        ctx.replace_articles(make_articles(1))
        assert ctx.article_count == 1

    def test_add_articles(self):
        ctx = ProcessingContext(articles=make_articles(2))
        ctx.add_articles(make_articles(1))
        assert ctx.article_count == 3

    def test_record_error(self):
        ctx = ProcessingContext()
        ctx.record_error("stage", "error msg", article_id="id1")
        assert ctx.has_errors
        assert ctx.errors[0].stage == "stage"

    def test_metadata_get_set(self):
        ctx = ProcessingContext()
        ctx.set("foo", 42)
        assert ctx.get("foo") == 42
        assert ctx.get("bar", "default") == "default"

    def test_abort(self):
        ctx = ProcessingContext()
        assert not ctx.is_aborted
        ctx.abort("too many errors")
        assert ctx.is_aborted
        assert ctx.get("abort_reason") == "too many errors"

    def test_run_id_generated(self):
        ctx = ProcessingContext()
        assert ctx.run_id
        assert len(ctx.run_id) > 0

    def test_custom_run_id(self):
        ctx = ProcessingContext(run_id="my-run-42")
        assert ctx.run_id == "my-run-42"

    def test_elapsed_ms(self):
        ctx = ProcessingContext()
        assert ctx.elapsed_ms >= 0.0

    def test_summary_structure(self):
        ctx = ProcessingContext(source_id="src")
        s = ctx.summary()
        assert s["source_id"] == "src"
        assert "run_id" in s
        assert "stages" in s

    def test_record_stage_updates_traces(self):
        arts = make_articles(2)
        ctx = ProcessingContext(articles=arts)
        result = ProcessingResult.from_articles("clean", 2, arts[:1], duration_ms=5.0)
        ctx.record_stage(result)
        assert len(ctx.stage_traces) == 1
        assert ctx.stage_traces[0].stage_name == "clean"


# ---------------------------------------------------------------------------
# BaseProcessor / PassthroughProcessor
# ---------------------------------------------------------------------------

class TestBaseProcessor:
    @pytest.mark.asyncio
    async def test_passthrough_leaves_articles_intact(self):
        arts = make_articles(3)
        ctx = ProcessingContext(articles=arts)
        proc = PassthroughProcessor()
        result = await proc.run(ctx)
        assert result.output_count == 3
        assert ctx.article_count == 3

    @pytest.mark.asyncio
    async def test_disabled_processor_is_noop(self):
        arts = make_articles(4)
        ctx = ProcessingContext(articles=arts)
        proc = FilterEvenProcessor(name="filter", enabled=False)
        result = await proc.run(ctx)
        assert result.output_count == 4      # no filtering when disabled

    @pytest.mark.asyncio
    async def test_filter_processor(self):
        arts = make_articles(4)
        ctx = ProcessingContext(articles=arts)
        proc = FilterEvenProcessor(name="filter")
        result = await proc.run(ctx)
        assert result.output_count == 2
        assert result.rejected_count == 2

    @pytest.mark.asyncio
    async def test_error_in_processor_captured(self):
        arts = make_articles(2)
        ctx = ProcessingContext(articles=arts)
        proc = BoomProcessor(name="boom")
        result = await proc.run(ctx)
        assert result.error_count == 1
        assert "boom" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_context_not_updated_on_error(self):
        """On fatal error the original articles are preserved in context."""
        arts = make_articles(2)
        ctx = ProcessingContext(articles=arts)
        proc = BoomProcessor(name="boom")
        await proc.run(ctx)
        # Articles should still be the originals (not empty)
        assert ctx.article_count == 2

    @pytest.mark.asyncio
    async def test_metadata_written_to_context(self):
        arts = make_articles(2)
        ctx = ProcessingContext(articles=arts)
        proc = MetadataProcessor(name="meta")
        await proc.run(ctx)
        assert ctx.get("processed_by") == "meta"

    @pytest.mark.asyncio
    async def test_stats_accumulated(self):
        arts = make_articles(4)
        ctx = ProcessingContext(articles=arts)
        proc = FilterEvenProcessor(name="filter")
        await proc.run(ctx)
        assert proc.stats["calls"] == 1
        assert proc.stats["total_processed"] == 2

    @pytest.mark.asyncio
    async def test_aborted_context_skips_processor(self):
        arts = make_articles(3)
        ctx = ProcessingContext(articles=arts)
        ctx.abort("test abort")
        proc = FilterEvenProcessor(name="filter")
        result = await proc.run(ctx)
        # empty result returned
        assert result.output_count == 0

    def test_repr(self):
        proc = PassthroughProcessor()
        assert "PassthroughProcessor" in repr(proc)


# ---------------------------------------------------------------------------
# ChainedProcessor
# ---------------------------------------------------------------------------

class TestChainedProcessor:
    @pytest.mark.asyncio
    async def test_chain_two_processors(self):
        arts = make_articles(4)   # 4 articles
        ctx = ProcessingContext(articles=arts)
        # FilterEven keeps 0,2 → 2 articles
        chained = FilterEvenProcessor(name="f1").chain(
            PassthroughProcessor(name="p1")
        )
        await chained.run(ctx)
        assert ctx.article_count == 2

    @pytest.mark.asyncio
    async def test_chain_three_processors(self):
        arts = make_articles(6)
        ctx = ProcessingContext(articles=arts)
        pipeline = (
            FilterEvenProcessor(name="f1")
            .chain(FilterEvenProcessor(name="f2"))
            .chain(PassthroughProcessor(name="p"))
        )
        await pipeline.run(ctx)
        assert ctx.article_count == 2

    @pytest.mark.asyncio
    async def test_chain_name(self):
        p1 = PassthroughProcessor(name="A")
        p2 = PassthroughProcessor(name="B")
        chained = p1.chain(p2)
        assert "A" in chained.name
        assert "B" in chained.name

    @pytest.mark.asyncio
    async def test_stage_traces_recorded_for_each_stage(self):
        arts = make_articles(4)
        ctx = ProcessingContext(articles=arts)
        p1 = FilterEvenProcessor(name="f1")
        p2 = PassthroughProcessor(name="p1")
        await p1.run(ctx)
        await p2.run(ctx)
        assert len(ctx.stage_traces) == 2
