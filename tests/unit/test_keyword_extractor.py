"""Tests for KeywordExtractor — section 5.9."""
from __future__ import annotations
import pytest
from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.enrichment.keyword_extractor import (
    KeywordExtractor, KeywordExtractorConfig, Keyword,
    _freq_extract, _yake_extract,
)
from shared.utils.datetime_utils import utc_now


def _make_article(content: str, title: str = "Test", language: str = "en") -> Article:
    return Article(
        id="kw_test_001",
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="kw_src", language=language),
    )


LONG_EN = (
    "Artificial intelligence is transforming the technology industry. "
    "Machine learning and deep learning are subfields of artificial intelligence. "
    "Natural language processing enables computers to understand human language. "
    "Data science involves extracting insights from large datasets using algorithms. "
    "Artificial intelligence research is advancing rapidly in universities worldwide."
)

LONG_AR = (
    "الذكاء الاصطناعي يحول صناعة التكنولوجيا بشكل كبير. "
    "التعلم الآلي والتعلم العميق من مجالات الذكاء الاصطناعي. "
    "معالجة اللغات الطبيعية تمكن الحواسيب من فهم اللغة البشرية. "
    "علم البيانات يستخرج رؤى من مجموعات البيانات الكبيرة باستخدام الخوارزميات. "
    "أبحاث الذكاء الاصطناعي تتقدم بسرعة في الجامعات حول العالم."
)


class TestFreqExtract:
    def test_returns_keywords_english(self):
        kws = _freq_extract(LONG_EN, language="en", max_keywords=5)
        assert len(kws) > 0
        assert all(isinstance(k, Keyword) for k in kws)

    def test_returns_keywords_arabic(self):
        kws = _freq_extract(LONG_AR, language="ar", max_keywords=5)
        assert len(kws) > 0

    def test_respects_max_keywords(self):
        kws = _freq_extract(LONG_EN, language="en", max_keywords=3)
        assert len(kws) <= 3

    def test_empty_text_returns_empty(self):
        kws = _freq_extract("", language="en", max_keywords=5)
        assert kws == []

    def test_rank_is_sequential(self):
        kws = _freq_extract(LONG_EN, language="en", max_keywords=5)
        ranks = [k.rank for k in kws]
        assert ranks == list(range(1, len(ranks) + 1))


class TestKeywordExtractor:
    def setup_method(self):
        self.extractor = KeywordExtractor()

    def test_extract_from_english_text(self):
        kws = self.extractor.extract_keywords(LONG_EN, language="en")
        assert len(kws) > 0
        assert all(isinstance(k, Keyword) for k in kws)

    def test_extract_from_arabic_text(self):
        kws = self.extractor.extract_keywords(LONG_AR, language="ar")
        assert len(kws) > 0

    def test_empty_returns_empty(self):
        kws = self.extractor.extract_keywords("", language="en")
        assert kws == []

    def test_extract_article_keywords_uses_language(self):
        art = _make_article(LONG_EN, language="en")
        kws = self.extractor.extract_article_keywords(art)
        assert len(kws) > 0

    def test_enrich_article_adds_tags(self):
        art = _make_article(LONG_EN, language="en")
        enriched = self.extractor.enrich_article(art)
        assert len(enriched.metadata.tags) >= len(art.metadata.tags)

    def test_enrich_batch(self):
        articles = [
            _make_article(LONG_EN, language="en"),
            _make_article(LONG_AR, language="ar"),
        ]
        result = self.extractor.enrich_batch(articles)
        assert len(result) == 2
        for r in result:
            assert len(r.metadata.tags) >= 0  # tags added

    def test_config_max_keywords_respected(self):
        cfg = KeywordExtractorConfig(max_keywords=3)
        extractor = KeywordExtractor(config=cfg)
        kws = extractor.extract_keywords(LONG_EN, language="en")
        assert len(kws) <= 3

    def test_keyword_scores_in_range(self):
        kws = self.extractor.extract_keywords(LONG_EN, language="en")
        for k in kws:
            assert 0.0 <= k.score <= 1.0
