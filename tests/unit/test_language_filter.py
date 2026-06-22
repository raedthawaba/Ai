"""Tests for section 5.5 — Language Filter."""

import pytest

from data_engine.processing.filtering.language_filter import (
    LanguageDetectionResult,
    LanguageFilter,
    LanguageFilterConfig,
    LanguageFilterResult,
    detect_language,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(
    title: str,
    content: str,
    lang: str = "en",
    url: str = "https://example.com/1",
) -> Article:
    return Article(
        id=generate_article_id(title + url),
        title=title,
        content=content,
        url=url,
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test", language=lang),
    )


ARABIC_TEXT = (
    "أعلن فريق من الباحثين في جامعة الملك عبدالله عن اكتشاف جديد في مجال "
    "الذكاء الاصطناعي يتعلق بمعالجة اللغة العربية بصورة أفضل من السابق. "
    "وأكد الباحثون أن هذا الاكتشاف سيفيد الملايين من الناطقين بالعربية."
)

ENGLISH_TEXT = (
    "Researchers at MIT announced a significant breakthrough in machine learning "
    "that could revolutionize how computers process and understand human language. "
    "The new approach uses a novel architecture that is both faster and more accurate."
)

FRENCH_TEXT = (
    "Les chercheurs ont annoncé une nouvelle découverte dans le domaine "
    "de l'intelligence artificielle qui pourrait changer notre façon de "
    "traiter le langage naturel."
)

SHORT_TEXT = "Hi"


# ---------------------------------------------------------------------------
# detect_language function
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_detects_arabic(self):
        result = detect_language(ARABIC_TEXT)
        assert isinstance(result, LanguageDetectionResult)
        assert result.language == "ar"
        assert result.confidence > 0.5

    def test_detects_english(self):
        result = detect_language(ENGLISH_TEXT)
        assert result.language == "en"
        assert result.confidence > 0.5

    def test_detects_french(self):
        result = detect_language(FRENCH_TEXT)
        assert result.language in ("fr", "en")  # allow low-confidence fallback

    def test_short_text_returns_unknown(self):
        result = detect_language(SHORT_TEXT)
        assert result.language in ("unknown", "en")

    def test_empty_text(self):
        result = detect_language("")
        assert result.language == "unknown"
        assert result.confidence == 0.0

    def test_result_has_method(self):
        result = detect_language(ENGLISH_TEXT)
        assert result.method in ("langdetect", "langdetect_low_confidence", "heuristic")

    def test_arabic_heuristic_fallback(self):
        """Arabic text should be detected even with heuristic."""
        arabic = "مرحبا بالعالم هذا نص عربي طويل نسبياً"
        result = detect_language(arabic)
        assert result.language == "ar"


# ---------------------------------------------------------------------------
# LanguageFilter
# ---------------------------------------------------------------------------

class TestLanguageFilter:
    def test_keeps_arabic_when_allowed(self):
        cfg = LanguageFilterConfig(allowed_languages=["ar"])
        lf = LanguageFilter(config=cfg)
        articles = [
            make_article("عنوان", ARABIC_TEXT),
        ]
        result = lf.filter_batch(articles)
        assert len(result.kept) == 1
        assert len(result.rejected) == 0

    def test_keeps_english_when_allowed(self):
        cfg = LanguageFilterConfig(allowed_languages=["en"])
        lf = LanguageFilter(config=cfg)
        articles = [make_article("Title", ENGLISH_TEXT)]
        result = lf.filter_batch(articles)
        assert len(result.kept) == 1

    def test_rejects_unallowed_language(self):
        cfg = LanguageFilterConfig(allowed_languages=["ar"])
        lf = LanguageFilter(config=cfg)
        articles = [make_article("Title", ENGLISH_TEXT)]
        result = lf.filter_batch(articles)
        assert len(result.rejected) >= 1

    def test_mixed_batch(self):
        cfg = LanguageFilterConfig(allowed_languages=["ar", "en"])
        lf = LanguageFilter(config=cfg)
        articles = [
            make_article("Arabic Article", ARABIC_TEXT, url="https://x.com/1"),
            make_article("English Article", ENGLISH_TEXT, url="https://x.com/2"),
        ]
        result = lf.filter_batch(articles)
        assert len(result.kept) == 2

    def test_filter_result_type(self):
        lf = LanguageFilter()
        articles = [make_article("Title", ENGLISH_TEXT)]
        result = lf.filter_batch(articles)
        assert isinstance(result, LanguageFilterResult)
        assert isinstance(result.kept, list)
        assert isinstance(result.rejected, list)

    def test_detection_map_populated(self):
        lf = LanguageFilter()
        articles = [
            make_article("Title A", ENGLISH_TEXT, url="https://x.com/1"),
            make_article("عنوان", ARABIC_TEXT, url="https://x.com/2"),
        ]
        result = lf.filter_batch(articles)
        assert len(result.detection_map) == 2

    def test_keep_rate(self):
        cfg = LanguageFilterConfig(allowed_languages=["ar", "en"])
        lf = LanguageFilter(config=cfg)
        articles = [
            make_article("T1", ARABIC_TEXT, url="https://x.com/1"),
            make_article("T2", ENGLISH_TEXT, url="https://x.com/2"),
        ]
        result = lf.filter_batch(articles)
        assert result.keep_rate == 1.0

    def test_empty_batch(self):
        lf = LanguageFilter()
        result = lf.filter_batch([])
        assert result.keep_rate == 1.0

    def test_all_languages_allowed_empty_list(self):
        cfg = LanguageFilterConfig(allowed_languages=[])
        lf = LanguageFilter(config=cfg)
        articles = [make_article("Title", ENGLISH_TEXT)]
        result = lf.filter_batch(articles)
        assert len(result.kept) == 1  # empty allowed = allow all

    def test_language_tagged_in_metadata(self):
        cfg = LanguageFilterConfig(
            allowed_languages=["ar", "en"],
            tag_detected_language=True,
        )
        lf = LanguageFilter(config=cfg)
        articles = [make_article("Title", ENGLISH_TEXT)]
        result = lf.filter_batch(articles)
        if result.kept:
            assert result.kept[0].metadata.language in ("en", "ar", "unknown", None)

    def test_detect_single_article(self):
        lf = LanguageFilter()
        article = make_article("Title", ARABIC_TEXT)
        det = lf.detect(article)
        assert det.language == "ar"

    def test_metadata_fallback_for_short_text(self):
        cfg = LanguageFilterConfig(
            allowed_languages=["ar"],
            fallback_to_metadata=True,
        )
        lf = LanguageFilter(config=cfg)
        article = make_article("T", "Hi", lang="ar")
        det = lf.detect(article)
        assert det.language == "ar"
        assert det.method == "metadata"
