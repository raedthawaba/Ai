"""Tests for ContentFilter — section 4.11."""

from __future__ import annotations

import pytest

from data_engine.processing.filtering.content_filter import (
    ContentFilter,
    FilterConfig,
    FilterResult,
    compute_quality_score,
    detect_language,
    is_arabic,
    _content_hash,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(
    title: str = "عنوان المقال التجريبي",
    content: str = "هذا محتوى المقال التجريبي الذي يحتوي على معلومات مفيدة وكافية.",
    url: str = "https://example.com/article",
    language: str = "ar",
    author: str = None,
    tags: list = None,
    summary: str = None,
) -> Article:
    return Article(
        id=generate_article_id(url + title),
        title=title,
        content=content,
        url=url,  # type: ignore[arg-type]
        published_at=utc_now(),
        summary=summary,
        metadata=ArticleMetadata(
            source_id="test",
            language=language,
            author=author,
            tags=tags or [],
        ),
    )


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

def test_detect_arabic():
    assert detect_language("هذا نص عربي طويل نسبياً") == "ar"


def test_detect_english():
    assert detect_language("This is a long English text with many letters") == "en"


def test_detect_unknown_empty():
    assert detect_language("") == "unknown"


def test_detect_unknown_digits():
    assert detect_language("12345 67890") == "unknown"


def test_detect_mixed_arabic_dominant():
    assert detect_language("نص عربي طويل جداً مع كلمات عديدة وكثيرة yes") == "ar"


def test_detect_mixed_english_dominant():
    assert detect_language("Long English text with كلمة one Arabic word") == "en"


# ---------------------------------------------------------------------------
# is_arabic
# ---------------------------------------------------------------------------

def test_is_arabic_true():
    assert is_arabic("هذا نص عربي طويل") is True


def test_is_arabic_false():
    assert is_arabic("This is English") is False


# ---------------------------------------------------------------------------
# compute_quality_score
# ---------------------------------------------------------------------------

def test_quality_score_range():
    a = _make_article(
        content="x" * 500, author="Jane", tags=["tech"], summary="short"
    )
    score = compute_quality_score(a)
    assert 0.0 <= score <= 1.0


def test_quality_score_longer_content_higher():
    short = _make_article(content="short")
    long_ = _make_article(content="x" * 800, url="https://example.com/long")
    assert compute_quality_score(long_) > compute_quality_score(short)


def test_quality_score_author_bonus():
    without = _make_article()
    with_ = _make_article(author="Jane Doe", url="https://example.com/author")
    assert compute_quality_score(with_) > compute_quality_score(without)


def test_quality_score_tags_bonus():
    without = _make_article()
    with_ = _make_article(tags=["tech", "ai"], url="https://example.com/tags")
    assert compute_quality_score(with_) > compute_quality_score(without)


# ---------------------------------------------------------------------------
# ContentFilter — length checks
# ---------------------------------------------------------------------------

def test_filter_rejects_short_title():
    cfg = FilterConfig(min_title_length=10)
    f = ContentFilter(cfg)
    a = _make_article(title="Hi")
    result = f.filter_batch([a])
    assert len(result.kept) == 0
    assert len(result.rejected) == 1
    assert "title_too_short" in result.rejection_reasons[a.id]


def test_filter_rejects_short_content():
    cfg = FilterConfig(min_content_length=100)
    f = ContentFilter(cfg)
    a = _make_article(content="Too short.")
    result = f.filter_batch([a])
    assert len(result.rejected) == 1
    assert "content_too_short" in result.rejection_reasons[a.id]


def test_filter_rejects_long_content():
    cfg = FilterConfig(max_content_length=50)
    f = ContentFilter(cfg)
    a = _make_article(content="x" * 200)
    result = f.filter_batch([a])
    assert len(result.rejected) == 1


def test_filter_keeps_valid_article():
    f = ContentFilter()
    a = _make_article()
    result = f.filter_batch([a])
    assert len(result.kept) == 1


# ---------------------------------------------------------------------------
# ContentFilter — language filter
# ---------------------------------------------------------------------------

def test_filter_allowed_language_arabic():
    cfg = FilterConfig(allowed_languages=["ar"])
    f = ContentFilter(cfg)
    ar_art = _make_article(language="ar")
    en_art = _make_article(
        title="English Article",
        content="This is an English article with enough content.",
        url="https://example.com/en",
        language="en",
    )
    result = f.filter_batch([ar_art, en_art])
    assert len(result.kept) == 1
    assert result.kept[0].metadata.language == "ar"


def test_filter_multiple_allowed_languages():
    cfg = FilterConfig(allowed_languages=["ar", "en"])
    f = ContentFilter(cfg)
    ar = _make_article(language="ar")
    en = _make_article(
        title="English Article",
        content="This is an English article.",
        url="https://example.com/en",
        language="en",
    )
    result = f.filter_batch([ar, en])
    assert len(result.kept) == 2


# ---------------------------------------------------------------------------
# ContentFilter — keyword filters
# ---------------------------------------------------------------------------

def test_filter_blocked_keyword():
    cfg = FilterConfig(blocked_keywords=["spam", "advertisement"])
    f = ContentFilter(cfg)
    a = _make_article(
        title="This is a spam article",
        content="Buy now! This spam content is useless.",
    )
    result = f.filter_batch([a])
    assert len(result.rejected) == 1
    assert "blocked_keyword" in result.rejection_reasons[a.id]


def test_filter_blocked_keyword_case_insensitive():
    cfg = FilterConfig(blocked_keywords=["SPAM"], keyword_case_sensitive=False)
    f = ContentFilter(cfg)
    a = _make_article(content="This is spam content that should be blocked.")
    result = f.filter_batch([a])
    assert len(result.rejected) == 1


def test_filter_required_keyword_present():
    cfg = FilterConfig(required_keywords=["python"])
    f = ContentFilter(cfg)
    a = _make_article(
        title="Python Programming",
        content="Learn python programming with this guide.",
        language="en",
    )
    result = f.filter_batch([a])
    assert len(result.kept) == 1


def test_filter_required_keyword_missing():
    cfg = FilterConfig(required_keywords=["blockchain"])
    f = ContentFilter(cfg)
    a = _make_article(
        content="This article is about machine learning and AI topics.",
        language="en",
    )
    result = f.filter_batch([a])
    assert len(result.rejected) == 1
    assert result.rejection_reasons[a.id] == "required_keyword_missing"


# ---------------------------------------------------------------------------
# ContentFilter — deduplication
# ---------------------------------------------------------------------------

def test_filter_deduplicates_urls():
    cfg = FilterConfig(deduplicate_urls=True)
    f = ContentFilter(cfg)
    a1 = _make_article(url="https://example.com/same")
    a2 = _make_article(url="https://example.com/same", title="Same URL duplicate")
    result = f.filter_batch([a1, a2])
    assert len(result.kept) == 1
    assert len(result.rejected) == 1


def test_filter_no_dedup_across_resets():
    cfg = FilterConfig(deduplicate_urls=True)
    f = ContentFilter(cfg)
    a = _make_article()
    f.filter_batch([a])
    f.reset()
    result = f.filter_batch([a])
    assert len(result.kept) == 1


def test_filter_deduplicates_content():
    cfg = FilterConfig(deduplicate_content=True)
    f = ContentFilter(cfg)
    a1 = _make_article(
        url="https://example.com/art1",
        content="نص المقال الذي يتكرر بشكل مطابق.",
    )
    a2 = _make_article(
        url="https://example.com/art2",
        content="نص المقال الذي يتكرر بشكل مطابق.",
    )
    result = f.filter_batch([a1, a2])
    assert len(result.kept) == 1


# ---------------------------------------------------------------------------
# ContentFilter — quality score
# ---------------------------------------------------------------------------

def test_filter_quality_threshold():
    cfg = FilterConfig(min_quality_score=0.5)
    f = ContentFilter(cfg)
    good = _make_article(
        content="x" * 600,
        author="Author",
        tags=["tech"],
        summary="Summary",
        url="https://example.com/good",
    )
    poor = _make_article(
        content="short",
        url="https://example.com/poor",
    )
    result = f.filter_batch([good, poor])
    assert good in result.kept


# ---------------------------------------------------------------------------
# FilterResult
# ---------------------------------------------------------------------------

def test_filter_result_keep_rate():
    cfg = FilterConfig(min_content_length=100)
    f = ContentFilter(cfg)
    articles = [
        _make_article(content="x" * 200, url=f"https://example.com/{i}")
        for i in range(7)
    ] + [
        _make_article(content="short", url=f"https://example.com/s{i}")
        for i in range(3)
    ]
    result = f.filter_batch(articles)
    assert abs(result.keep_rate - 0.7) < 0.01
    assert result.total == 10


def test_filter_result_empty():
    f = ContentFilter()
    result = f.filter_batch([])
    assert result.total == 0
    assert result.keep_rate == 0.0


# ---------------------------------------------------------------------------
# is_allowed (stateless)
# ---------------------------------------------------------------------------

def test_is_allowed_true():
    f = ContentFilter()
    a = _make_article()
    assert f.is_allowed(a) is True


def test_is_allowed_false():
    cfg = FilterConfig(min_title_length=100)
    f = ContentFilter(cfg)
    a = _make_article(title="Short")
    assert f.is_allowed(a) is False
