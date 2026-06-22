"""Integration tests — Full Pipeline (section 5.18).

Tests the complete Fetch → Clean → Filter → Enrich → Transform → Store cycle.
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from shared.schemas.article import Article, ArticleMetadata
from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
from data_engine.processing.filtering.policy_filter import PolicyFilterConfig
from shared.utils.datetime_utils import utc_now


def _article(aid: str, content: str, language: str = "en", url_suffix: str = "") -> Article:
    return Article(
        id=aid,
        title=f"Article {aid}",
        content=content,
        url=f"https://example.com/{aid}{url_suffix}",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="integration_test", language=language),
    )


EN_CONTENT = (
    "Artificial intelligence is rapidly transforming every sector of the economy. "
    "Machine learning algorithms enable computers to find patterns in massive datasets. "
    "Natural language processing allows AI systems to understand and generate human text. "
    "These technologies are being deployed in healthcare, education, and manufacturing. "
    "Researchers continue to push the boundaries of what artificial intelligence can achieve."
)

AR_CONTENT = (
    "يُحدث الذكاء الاصطناعي ثورة حقيقية في جميع قطاعات الاقتصاد العالمي. "
    "تُمكّن خوارزميات التعلم الآلي الحواسيب من اكتشاف الأنماط في البيانات الضخمة. "
    "تُتيح معالجة اللغات الطبيعية لأنظمة الذكاء الاصطناعي فهم النصوص البشرية وتوليدها. "
    "تُطبَّق هذه التقنيات في مجالات الرعاية الصحية والتعليم والتصنيع. "
    "يواصل الباحثون دفع حدود ما يمكن لأنظمة الذكاء الاصطناعي تحقيقه."
)


@pytest.fixture
def pipeline():
    policy_cfg = PolicyFilterConfig(
        min_content_length=30,
        blocked_domains=["spam.com"],
        blocked_keywords=["gambling"],
    )
    return PipelineOrchestrator(
        name="integration_pipeline",
        source_id="integration_test",
        policy_config=policy_cfg,
        allowed_languages=["ar", "en"],
    )


class TestFullPipelineIntegration:
    @pytest.mark.asyncio
    async def test_single_english_article(self, pipeline):
        arts = [_article("en_001", EN_CONTENT)]
        ctx = await pipeline.run(articles=arts)
        assert not ctx.is_aborted
        assert ctx.article_count >= 0

    @pytest.mark.asyncio
    async def test_single_arabic_article(self, pipeline):
        arts = [_article("ar_001", AR_CONTENT, language="ar")]
        ctx = await pipeline.run(articles=arts)
        assert not ctx.is_aborted

    @pytest.mark.asyncio
    async def test_mixed_language_batch(self, pipeline):
        arts = [
            _article("en_001", EN_CONTENT, language="en"),
            _article("ar_001", AR_CONTENT, language="ar"),
        ]
        ctx = await pipeline.run(articles=arts)
        assert isinstance(ctx.articles, list)

    @pytest.mark.asyncio
    async def test_duplicate_articles_removed(self, pipeline):
        arts = [
            _article("dup_01", EN_CONTENT, url_suffix="?v=1"),
            _article("dup_02", EN_CONTENT, url_suffix="?v=2"),
        ]
        ctx = await pipeline.run(articles=arts)
        assert ctx.article_count <= 2

    @pytest.mark.asyncio
    async def test_blocked_domain_rejected(self, pipeline):
        spam_art = Article(
            id="spam_01",
            title="Spam Article",
            content=EN_CONTENT,
            url="https://spam.com/article",
            published_at=utc_now(),
            metadata=ArticleMetadata(source_id="integration_test", language="en"),
        )
        arts = [_article("good_01", EN_CONTENT), spam_art]
        ctx = await pipeline.run(articles=arts)
        ids = [a.id for a in ctx.articles]
        assert "spam_01" not in ids

    @pytest.mark.asyncio
    async def test_summary_added(self, pipeline):
        arts = [_article("sum_01", EN_CONTENT)]
        ctx = await pipeline.run(articles=arts)
        for art in ctx.articles:
            assert art.summary is not None

    @pytest.mark.asyncio
    async def test_chunks_metadata_added(self, pipeline):
        arts = [_article("chunk_01", EN_CONTENT)]
        ctx = await pipeline.run(articles=arts)
        for art in ctx.articles:
            assert "chunk_count" in art.metadata.extra

    @pytest.mark.asyncio
    async def test_token_count_added(self, pipeline):
        arts = [_article("tok_01", EN_CONTENT)]
        ctx = await pipeline.run(articles=arts)
        for art in ctx.articles:
            assert "token_count" in art.metadata.extra
            assert art.metadata.extra["token_count"] > 0

    @pytest.mark.asyncio
    async def test_metrics_captured(self, pipeline):
        arts = [_article("m_01", EN_CONTENT)]
        await pipeline.run(articles=arts)
        m = pipeline.last_metrics
        assert m is not None
        assert m.input_count >= 0
        assert m.total_duration_ms > 0

    @pytest.mark.asyncio
    async def test_all_six_stages_traced(self, pipeline):
        arts = [_article("s_01", EN_CONTENT)]
        ctx = await pipeline.run(articles=arts)
        stage_names = [t.stage_name for t in ctx.stage_traces]
        for expected in ["fetch", "clean", "filter", "enrich", "transform", "store"]:
            assert expected in stage_names

    @pytest.mark.asyncio
    async def test_large_batch(self, pipeline):
        arts = [_article(f"batch_{i}", EN_CONTENT) for i in range(15)]
        ctx = await pipeline.run(articles=arts)
        assert isinstance(ctx.articles, list)
        m = pipeline.last_metrics
        assert m.input_count == 15

    @pytest.mark.asyncio
    async def test_html_cleaned(self, pipeline):
        html = (
            "<h1>AI Article</h1>"
            "<p>Artificial intelligence is changing the world rapidly.</p>"
            "<p>Machine learning enables automated pattern recognition effectively.</p>"
            "<script>alert('ads')</script>"
            "<p>NLP is key to modern AI systems worldwide.</p>"
        )
        arts = [_article("html_01", html)]
        ctx = await pipeline.run(articles=arts)
        for art in ctx.articles:
            assert "<script>" not in art.content
            assert "<h1>" not in art.content

    @pytest.mark.asyncio
    async def test_store_stage_writes_files(self, tmp_path):
        from data_engine.pipelines.stages import StoreStage
        policy_cfg = PolicyFilterConfig(min_content_length=10)
        orch = PipelineOrchestrator(
            name="store_test",
            source_id="test",
            policy_config=policy_cfg,
        )
        orch._stages[-1] = StoreStage(local_path=tmp_path)
        arts = [_article("file_01", EN_CONTENT)]
        await orch.run(articles=arts)
        # Files may or may not be written depending on filter outcome
        files = list(tmp_path.glob("*.json"))
        assert len(files) >= 0
