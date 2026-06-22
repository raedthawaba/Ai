"""Tests for ContentEnricher — section 4.12."""

from __future__ import annotations

import pytest

from data_engine.processing.enrichment.content_enricher import (
    ContentEnricher,
    EnricherConfig,
    estimate_reading_time,
    extract_date_hints,
    extract_hashtags,
    extract_keywords,
    extractive_summary,
    split_sentences,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(
    title: str = "عنوان تجريبي للمقال",
    content: str = "هذا هو المحتوى الأساسي للمقال. يحتوي على معلومات مفيدة. سيتم استخدامه للاختبار.",
    language: str = "ar",
    tags: list = None,
    summary: str = None,
) -> Article:
    return Article(
        id=generate_article_id(title + content[:20]),
        title=title,
        content=content,
        url="https://example.com/article",  # type: ignore[arg-type]
        published_at=utc_now(),
        summary=summary,
        metadata=ArticleMetadata(
            source_id="test",
            language=language,
            tags=tags or [],
        ),
    )


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------

def test_split_sentences_english():
    text = "Hello world. How are you? I am fine!"
    sentences = split_sentences(text)
    assert len(sentences) == 3


def test_split_sentences_arabic():
    text = "هذه الجملة الأولى. وهذه هي الثانية! والثالثة؟"
    sentences = split_sentences(text)
    assert len(sentences) >= 2


def test_split_sentences_empty():
    assert split_sentences("") == []


def test_split_sentences_single():
    assert split_sentences("One sentence only") == ["One sentence only"]


# ---------------------------------------------------------------------------
# extractive_summary
# ---------------------------------------------------------------------------

def test_extractive_summary_default():
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    summary = extractive_summary(text, max_sentences=3)
    assert "First sentence" in summary
    assert "Second sentence" in summary
    assert "Third sentence" in summary
    assert "Fourth sentence" not in summary


def test_extractive_summary_fewer_sentences():
    text = "Only one sentence here."
    summary = extractive_summary(text, max_sentences=3)
    assert summary == "Only one sentence here."


def test_extractive_summary_empty():
    assert extractive_summary("") == ""


def test_extractive_summary_max_1():
    text = "First. Second. Third."
    assert "Second" not in extractive_summary(text, max_sentences=1)


# ---------------------------------------------------------------------------
# estimate_reading_time
# ---------------------------------------------------------------------------

def test_estimate_reading_time_arabic():
    text = " ".join(["كلمة"] * 138)
    secs = estimate_reading_time(text)
    assert 50 <= secs <= 80


def test_estimate_reading_time_english():
    text = " ".join(["word"] * 200)
    secs = estimate_reading_time(text)
    assert 50 <= secs <= 80


def test_estimate_reading_time_empty():
    assert estimate_reading_time("") == 1


def test_estimate_reading_time_returns_int():
    assert isinstance(estimate_reading_time("some text here"), int)


def test_estimate_reading_time_minimum_one():
    assert estimate_reading_time("a") >= 1


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------

def test_extract_keywords_english():
    text = "Python programming language is great. Python developers love Python."
    kws = extract_keywords(text, language="en", max_keywords=5)
    assert "python" in kws


def test_extract_keywords_arabic():
    text = "البرمجة بلغة بايثون ممتازة. يحب المطورون استخدام بايثون في مشاريعهم."
    kws = extract_keywords(text, language="ar", max_keywords=5)
    assert len(kws) > 0


def test_extract_keywords_title_boost():
    text = "machine learning is a subfield of artificial intelligence"
    kws = extract_keywords(
        text, language="en", title_text="machine learning guide", title_boost=5
    )
    assert "machine" in kws or "learning" in kws


def test_extract_keywords_max_limit():
    text = " ".join([f"unique{i}" for i in range(50)])
    kws = extract_keywords(text, language="en", max_keywords=10)
    assert len(kws) <= 10


def test_extract_keywords_min_length():
    text = "do it now and go for it quickly"
    kws = extract_keywords(text, language="en", min_length=4)
    assert all(len(k) >= 4 for k in kws)


def test_extract_keywords_stop_words_excluded():
    text = "من في على إلى عن مع هذا ذلك"
    kws = extract_keywords(text, language="ar")
    assert all(k not in {"من", "في", "على", "إلى", "عن", "مع", "هذا", "ذلك"} for k in kws)


# ---------------------------------------------------------------------------
# extract_hashtags
# ---------------------------------------------------------------------------

def test_extract_hashtags_basic():
    text = "Trending #Python and #AI today!"
    hashtags = extract_hashtags(text)
    assert "Python" in hashtags
    assert "AI" in hashtags


def test_extract_hashtags_none():
    assert extract_hashtags("No hashtags here.") == []


def test_extract_hashtags_arabic():
    text = "موضوع #تعلم_الالة رائع"
    hashtags = extract_hashtags(text)
    assert len(hashtags) >= 1


# ---------------------------------------------------------------------------
# extract_date_hints
# ---------------------------------------------------------------------------

def test_extract_date_hints_iso():
    text = "Published on 2024-05-20 and updated 2024-06-01."
    entities = extract_date_hints(text)
    texts = [e.text for e in entities]
    assert "2024-05-20" in texts


def test_extract_date_hints_slash():
    text = "Event on 20/05/2024 is confirmed."
    entities = extract_date_hints(text)
    assert len(entities) >= 1
    assert all(e.label == "DATE" for e in entities)


def test_extract_date_hints_none():
    text = "No dates in this text at all."
    assert extract_date_hints(text) == []


def test_extract_date_hints_score():
    entities = extract_date_hints("Happened on 2024-01-15.")
    assert all(0 < e.score <= 1.0 for e in entities)


# ---------------------------------------------------------------------------
# ContentEnricher.enrich_article
# ---------------------------------------------------------------------------

def test_enrich_adds_summary_when_missing():
    article = _make_article(
        content="الجملة الأولى في المقال. الجملة الثانية مهمة. الجملة الثالثة للاختبار."
    )
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    assert enriched.summary is not None
    assert len(enriched.summary) > 0


def test_enrich_does_not_overwrite_existing_summary():
    article = _make_article(summary="ملخص موجود مسبقاً.")
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    assert enriched.summary == "ملخص موجود مسبقاً."


def test_enrich_adds_reading_time():
    article = _make_article(content=" ".join(["كلمة"] * 200))
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    assert "reading_time_seconds" in enriched.metadata.extra
    assert enriched.metadata.extra["reading_time_seconds"] >= 1


def test_enrich_adds_keywords_to_tags():
    article = _make_article(
        content="Python programming is popular. Python developers build great apps.",
        language="en",
    )
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    assert len(enriched.metadata.tags) > 0


def test_enrich_merges_with_existing_tags():
    article = _make_article(tags=["existing_tag"])
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    assert "existing_tag" in enriched.metadata.tags


def test_enrich_adds_date_entities():
    article = _make_article(
        content="The conference starts on 2024-09-15 and ends on 2024-09-20."
    )
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    date_entities = [e for e in enriched.metadata.entities if e.label == "DATE"]
    assert len(date_entities) >= 1


def test_enrich_extracts_hashtags():
    article = _make_article(
        title="New #Python release",
        content="The new #Python release is amazing.",
    )
    enricher = ContentEnricher()
    enriched = enricher.enrich_article(article)
    tags_lower = [t.lower() for t in enriched.metadata.tags]
    assert "python" in tags_lower


def test_enrich_does_not_mutate_original():
    article = _make_article()
    original_tags = list(article.metadata.tags)
    enricher = ContentEnricher()
    _ = enricher.enrich_article(article)
    assert article.metadata.tags == original_tags


# ---------------------------------------------------------------------------
# ContentEnricher.enrich_batch
# ---------------------------------------------------------------------------

def test_enrich_batch():
    articles = [_make_article(title=f"عنوان {i}", content=f"محتوى المقال رقم {i} طويل بما يكفي.") for i in range(5)]
    enricher = ContentEnricher()
    result = enricher.enrich_batch(articles)
    assert len(result) == 5
    assert all("reading_time_seconds" in a.metadata.extra for a in result)


# ---------------------------------------------------------------------------
# EnricherConfig
# ---------------------------------------------------------------------------

def test_config_disable_summary():
    article = _make_article()
    enricher = ContentEnricher(config=EnricherConfig(generate_summary=False))
    enriched = enricher.enrich_article(article)
    assert enriched.summary is None


def test_config_disable_reading_time():
    article = _make_article()
    enricher = ContentEnricher(config=EnricherConfig(estimate_reading_time=False))
    enriched = enricher.enrich_article(article)
    assert "reading_time_seconds" not in enriched.metadata.extra


def test_config_disable_tags():
    article = _make_article()
    enricher = ContentEnricher(config=EnricherConfig(enrich_tags=False))
    enriched = enricher.enrich_article(article)
    assert len(enriched.metadata.tags) == 0
