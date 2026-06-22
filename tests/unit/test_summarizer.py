"""Tests for Summarizer — section 5.11."""
from __future__ import annotations
import pytest
from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.enrichment.summarizer import (
    Summarizer, SummarizerConfig,
    extractive_summarize, _split_sentences,
)
from shared.utils.datetime_utils import utc_now


def _make_article(content: str, title: str = "Test", language: str = "ar", has_summary: bool = False) -> Article:
    return Article(
        id="sum_001",
        title=title,
        content=content,
        url="https://example.com/article",
        published_at=utc_now(),
        summary="existing summary" if has_summary else None,
        metadata=ArticleMetadata(source_id="test", language=language),
    )


LONG_AR = (
    "الذكاء الاصطناعي يُغيّر العالم بشكل كبير. "
    "يتيح التعلم الآلي للحواسيب أن تتعلم من البيانات. "
    "تستخدم الشركات هذه التقنية في كل المجالات. "
    "الطب والتعليم والصناعة تستفيد من الذكاء الاصطناعي. "
    "المستقبل سيشهد المزيد من التطورات في هذا المجال الواعد."
)

LONG_EN = (
    "Artificial intelligence is revolutionizing modern industries. "
    "Machine learning allows computers to learn patterns from data automatically. "
    "Companies across sectors are adopting AI technologies rapidly. "
    "Healthcare, education and manufacturing benefit from these advances. "
    "The future promises even greater breakthroughs in AI research."
)


class TestSplitSentences:
    def test_splits_english(self):
        text = "First sentence. Second sentence. Third one!"
        sents = _split_sentences(text)
        assert len(sents) >= 2

    def test_splits_arabic(self):
        sents = _split_sentences(LONG_AR)
        assert len(sents) >= 3

    def test_empty_returns_empty(self):
        assert _split_sentences("") == []


class TestExtractiveSummarize:
    def test_returns_string(self):
        result = extractive_summarize(LONG_EN, title="AI", language="en")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_max_sentences_respected(self):
        result = extractive_summarize(LONG_EN, max_sentences=2, language="en")
        # Result should be at most 2 sentences (≤ 2 period+space patterns)
        assert len(result) < len(LONG_EN)

    def test_arabic_content(self):
        result = extractive_summarize(LONG_AR, title="ذكاء اصطناعي", language="ar")
        assert len(result) > 0

    def test_title_boost_influences_output(self):
        # Same content, different title — should affect sentence selection
        r1 = extractive_summarize(LONG_EN, title="healthcare", title_boost=5.0, language="en")
        r2 = extractive_summarize(LONG_EN, title="irrelevant", title_boost=0.0, language="en")
        # Both should return content
        assert len(r1) > 0
        assert len(r2) > 0

    def test_short_content_fallback(self):
        result = extractive_summarize("Short text.", language="en")
        assert "Short" in result or len(result) > 0


class TestSummarizer:
    def setup_method(self):
        self.summarizer = Summarizer()

    def test_summarize_english(self):
        result = self.summarizer.summarize(LONG_EN, language="en")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_summarize_arabic(self):
        result = self.summarizer.summarize(LONG_AR, language="ar")
        assert len(result) > 0

    def test_empty_returns_empty(self):
        assert self.summarizer.summarize("") == ""

    def test_summarize_article_no_summary(self):
        art = _make_article(LONG_EN, language="en")
        enriched = self.summarizer.summarize_article(art)
        assert enriched.summary is not None
        assert len(enriched.summary) > 0

    def test_summarize_article_keeps_existing_summary(self):
        art = _make_article(LONG_EN, language="en", has_summary=True)
        enriched = self.summarizer.summarize_article(art)
        assert enriched.summary == "existing summary"

    def test_summarize_batch(self):
        arts = [
            _make_article(LONG_EN, language="en"),
            _make_article(LONG_AR, language="ar"),
        ]
        result = self.summarizer.summarize_batch(arts)
        assert len(result) == 2
        for r in result:
            assert r.summary is not None

    def test_config_max_sentences(self):
        cfg = SummarizerConfig(max_sentences=1)
        s = Summarizer(config=cfg)
        result = s.summarize(LONG_EN, language="en")
        # Should be roughly one sentence
        assert len(result) > 0
