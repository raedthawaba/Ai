"""Tests for PipelineOrchestrator — section 5.15."""
from __future__ import annotations
import pytest
from pathlib import Path
from shared.schemas.article import Article, ArticleMetadata
from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator, PipelineMetrics
from data_engine.pipelines.base_pipeline import BasePipeline
from data_engine.processing.processing_context import ProcessingContext
from data_engine.processing.filtering.policy_filter import PolicyFilterConfig
from shared.utils.datetime_utils import utc_now


def _make_article(
    content: str = "This article covers artificial intelligence and machine learning developments in modern society.",
    url: str = "https://example.com/article",
    title: str = "AI Progress",
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


class TestBasePipeline:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BasePipeline("test")  # can't instantiate abstract class

    def test_add_stage_returns_self(self):
        from data_engine.pipelines.stages import FetchStage
        class ConcretePipeline(BasePipeline):
            async def run(self, articles=None, config=None):
                return ProcessingContext()
        p = ConcretePipeline("test")
        stage = FetchStage()
        result = p.add_stage(stage)
        assert result is p
        assert len(p.stages) == 1


class TestPipelineOrchestrator:
    def _make_orchestrator(self, tmp_path: Path) -> PipelineOrchestrator:
        policy_cfg = PolicyFilterConfig(min_content_length=10)
        return PipelineOrchestrator(
            name="test_pipeline",
            source_id="test",
            policy_config=policy_cfg,
            allowed_languages=["ar", "en"],
        )

    @pytest.mark.asyncio
    async def test_run_with_articles(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        arts = [_make_article(aid=f"art_{i}") for i in range(3)]
        ctx = await orch.run(articles=arts)
        assert isinstance(ctx, ProcessingContext)
        assert ctx.run_id is not None

    @pytest.mark.asyncio
    async def test_run_produces_context_summary(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        arts = [_make_article()]
        ctx = await orch.run(articles=arts)
        summary = ctx.summary()
        assert "run_id" in summary
        assert "stages" in summary
        assert len(summary["stages"]) > 0

    @pytest.mark.asyncio
    async def test_metrics_available_after_run(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        assert orch.last_metrics is None
        await orch.run(articles=[_make_article()])
        metrics = orch.last_metrics
        assert isinstance(metrics, PipelineMetrics)
        assert metrics.pipeline_name == "test_pipeline"

    @pytest.mark.asyncio
    async def test_metrics_rejection_rate(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        arts = [_make_article(aid=str(i)) for i in range(5)]
        await orch.run(articles=arts)
        metrics = orch.last_metrics
        assert 0.0 <= metrics.rejection_rate <= 1.0

    @pytest.mark.asyncio
    async def test_run_empty_articles(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        ctx = await orch.run(articles=[])
        assert isinstance(ctx, ProcessingContext)

    @pytest.mark.asyncio
    async def test_pipeline_has_six_stages(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        assert len(orch.stages) == 6

    @pytest.mark.asyncio
    async def test_fetch_fn_integration(self, tmp_path):
        async def mock_fetch():
            return [_make_article(aid="fetched")]
        policy_cfg = PolicyFilterConfig(min_content_length=10)
        orch = PipelineOrchestrator(
            name="fetch_test",
            source_id="test",
            fetch_fn=mock_fetch,
            policy_config=policy_cfg,
        )
        ctx = await orch.run(articles=[])
        # Fetch fn should have added an article
        assert ctx.get("fetch_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_arabic_articles_processed(self, tmp_path):
        orch = self._make_orchestrator(tmp_path)
        ar_art = _make_article(
            content="الذكاء الاصطناعي يُغيّر العالم بشكل كبير جداً ومتسارع في مجالات كثيرة ومتنوعة.",
            title="تقنية الذكاء الاصطناعي",
            language="ar",
            aid="ar_001",
        )
        ctx = await orch.run(articles=[ar_art])
        assert isinstance(ctx, ProcessingContext)


class TestPipelineMetrics:
    def test_rejection_rate_calculation(self):
        m = PipelineMetrics(
            pipeline_name="test", run_id="r1",
            input_count=10, output_count=7
        )
        assert abs(m.rejection_rate - 0.3) < 0.001

    def test_rejection_rate_zero_input(self):
        m = PipelineMetrics(pipeline_name="test", run_id="r1")
        assert m.rejection_rate == 0.0

    def test_summary_has_required_keys(self):
        m = PipelineMetrics(pipeline_name="test", run_id="r1", input_count=5, output_count=3)
        s = m.summary()
        assert "pipeline" in s
        assert "input" in s
        assert "output" in s
        assert "rejection_rate" in s
        assert "duration_ms" in s
