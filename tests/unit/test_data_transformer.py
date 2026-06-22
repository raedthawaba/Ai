"""Tests for DataTransformer — section 4.13."""

from __future__ import annotations

import json
from datetime import timezone

import pytest

from data_engine.processing.transformation.data_transformer import (
    DataTransformer,
    TransformerConfig,
    article_to_dict,
    article_to_json,
    articles_to_dicts,
    articles_to_jsonl,
    get_csv_headers,
    OUTPUT_FORMAT_COMPACT,
    OUTPUT_FORMAT_CSV,
    OUTPUT_FORMAT_FLAT,
    OUTPUT_FORMAT_FULL,
)
from shared.schemas.article import Article, ArticleMetadata, ArticleEntity
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(
    title: str = "Test Article Title",
    content: str = "This is the full article content for testing purposes.",
    url: str = "https://example.com/test",
    language: str = "en",
    author: str = "Jane Doe",
    tags: list = None,
    summary: str = "Short summary.",
) -> Article:
    return Article(
        id=generate_article_id(url + title),
        title=title,
        content=content,
        url=url,  # type: ignore[arg-type]
        published_at=utc_now(),
        summary=summary,
        metadata=ArticleMetadata(
            source_id="test_source",
            language=language,
            author=author,
            tags=tags or ["tech", "news"],
            extra={"reading_time_seconds": 45},
        ),
    )


ARTICLE = _make_article()


# ---------------------------------------------------------------------------
# article_to_dict — full format
# ---------------------------------------------------------------------------

def test_full_format_has_required_fields():
    data = article_to_dict(ARTICLE)
    for key in ("id", "title", "content", "url", "published_at", "metadata"):
        assert key in data


def test_full_format_metadata_block():
    data = article_to_dict(ARTICLE)
    meta = data["metadata"]
    assert meta["source_id"] == "test_source"
    assert meta["language"] == "en"
    assert meta["author"] == "Jane Doe"
    assert isinstance(meta["tags"], list)


def test_full_format_url_is_string():
    data = article_to_dict(ARTICLE)
    assert isinstance(data["url"], str)
    assert data["url"].startswith("https://")


def test_full_format_datetime_is_string():
    data = article_to_dict(ARTICLE)
    assert isinstance(data["published_at"], str)
    assert "T" in data["published_at"]


def test_full_format_entities_present():
    article = _make_article()
    entity = ArticleEntity(text="2024-05-20", label="DATE", start_char=0, end_char=10)
    new_meta = article.metadata.model_copy(update={"entities": [entity]})
    article = article.model_copy(update={"metadata": new_meta})
    data = article_to_dict(article, TransformerConfig(include_entities=True))
    entities = data["metadata"]["entities"]
    assert len(entities) == 1
    assert entities[0]["label"] == "DATE"


def test_full_format_no_entities_when_disabled():
    article = _make_article()
    entity = ArticleEntity(text="2024-05-20", label="DATE", start_char=0, end_char=10)
    new_meta = article.metadata.model_copy(update={"entities": [entity]})
    article = article.model_copy(update={"metadata": new_meta})
    data = article_to_dict(article, TransformerConfig(include_entities=False))
    assert "entities" not in data.get("metadata", {})


# ---------------------------------------------------------------------------
# article_to_dict — compact format
# ---------------------------------------------------------------------------

def test_compact_format_fields():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_COMPACT)
    data = article_to_dict(ARTICLE, cfg)
    assert "id" in data
    assert "title" in data
    assert "url" in data
    assert "language" in data
    assert "source_id" in data
    assert "tags" in data
    assert "content" not in data


# ---------------------------------------------------------------------------
# article_to_dict — flat format
# ---------------------------------------------------------------------------

def test_flat_format_promotes_metadata():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_FLAT)
    data = article_to_dict(ARTICLE, cfg)
    assert "metadata_source_id" in data
    assert "metadata_language" in data
    assert "metadata_author" in data
    assert "metadata" not in data


def test_flat_format_tags_as_string():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_FLAT)
    data = article_to_dict(ARTICLE, cfg)
    assert isinstance(data["metadata_tags"], str)


def test_flat_format_reading_time_promoted():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_FLAT)
    data = article_to_dict(ARTICLE, cfg)
    assert "metadata_reading_time_seconds" in data
    assert data["metadata_reading_time_seconds"] == 45


# ---------------------------------------------------------------------------
# article_to_dict — CSV format
# ---------------------------------------------------------------------------

def test_csv_format_scalar_values_only():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_CSV)
    data = article_to_dict(ARTICLE, cfg)
    for key, val in data.items():
        assert not isinstance(val, (dict, list)), f"field {key!r} is not scalar"


def test_csv_format_has_content_length():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_CSV)
    data = article_to_dict(ARTICLE, cfg)
    assert "content_length" in data
    assert data["content_length"] == len(ARTICLE.content)


def test_csv_format_tags_as_comma_string():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_CSV)
    data = article_to_dict(ARTICLE, cfg)
    assert isinstance(data["tags"], str)
    assert "," in data["tags"] or len(ARTICLE.metadata.tags) == 1


# ---------------------------------------------------------------------------
# field selection / renaming
# ---------------------------------------------------------------------------

def test_include_fields():
    cfg = TransformerConfig(include_fields=["id", "title"])
    data = article_to_dict(ARTICLE, cfg)
    assert set(data.keys()) == {"id", "title"}


def test_exclude_fields():
    cfg = TransformerConfig(exclude_fields=["content", "summary"])
    data = article_to_dict(ARTICLE, cfg)
    assert "content" not in data
    assert "summary" not in data


def test_field_renames():
    cfg = TransformerConfig(
        output_format=OUTPUT_FORMAT_COMPACT,
        field_renames={"title": "headline", "url": "link"},
    )
    data = article_to_dict(ARTICLE, cfg)
    assert "headline" in data
    assert "link" in data
    assert "title" not in data
    assert "url" not in data


# ---------------------------------------------------------------------------
# articles_to_dicts
# ---------------------------------------------------------------------------

def test_articles_to_dicts():
    articles = [_make_article(url=f"https://example.com/{i}", title=f"Article {i}") for i in range(5)]
    result = articles_to_dicts(articles)
    assert len(result) == 5
    assert all(isinstance(d, dict) for d in result)


def test_articles_to_dicts_empty():
    assert articles_to_dicts([]) == []


# ---------------------------------------------------------------------------
# article_to_json
# ---------------------------------------------------------------------------

def test_article_to_json_valid():
    js = article_to_json(ARTICLE)
    parsed = json.loads(js)
    assert parsed["id"] == ARTICLE.id


def test_article_to_json_arabic():
    ar = _make_article(
        title="عنوان المقال العربي",
        content="هذا محتوى المقال باللغة العربية.",
        language="ar",
        url="https://example.com/ar",
    )
    js = article_to_json(ar)
    assert "عنوان المقال العربي" in js


def test_article_to_json_indent():
    js = article_to_json(ARTICLE, indent=2)
    assert "\n" in js


# ---------------------------------------------------------------------------
# articles_to_jsonl
# ---------------------------------------------------------------------------

def test_articles_to_jsonl():
    articles = [_make_article(url=f"https://example.com/{i}", title=f"Art {i}") for i in range(3)]
    result = articles_to_jsonl(articles)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert "id" in obj


def test_articles_to_jsonl_empty():
    assert articles_to_jsonl([]) == ""


# ---------------------------------------------------------------------------
# get_csv_headers
# ---------------------------------------------------------------------------

def test_get_csv_headers_default():
    headers = get_csv_headers()
    assert "id" in headers
    assert "title" in headers
    assert "url" in headers


def test_get_csv_headers_with_renames():
    cfg = TransformerConfig(
        output_format=OUTPUT_FORMAT_CSV,
        field_renames={"title": "headline"},
    )
    headers = get_csv_headers(cfg)
    assert "headline" in headers
    assert "title" not in headers


# ---------------------------------------------------------------------------
# DataTransformer class
# ---------------------------------------------------------------------------

def test_data_transformer_transform():
    cfg = TransformerConfig(output_format=OUTPUT_FORMAT_COMPACT)
    t = DataTransformer(config=cfg)
    data = t.transform(ARTICLE)
    assert "id" in data
    assert "content" not in data


def test_data_transformer_custom_transform():
    def add_flag(article, data):
        data["custom_field"] = "injected"
        return data

    t = DataTransformer(custom_transform=add_flag)
    data = t.transform(ARTICLE)
    assert data["custom_field"] == "injected"


def test_data_transformer_transform_batch():
    t = DataTransformer()
    articles = [_make_article(url=f"https://example.com/{i}", title=f"A{i}") for i in range(4)]
    result = t.transform_batch(articles)
    assert len(result) == 4


def test_data_transformer_to_json():
    t = DataTransformer()
    js = t.to_json(ARTICLE)
    parsed = json.loads(js)
    assert parsed["title"] == ARTICLE.title


def test_data_transformer_to_jsonl():
    t = DataTransformer()
    articles = [_make_article(url=f"https://example.com/{i}", title=f"Art {i}") for i in range(3)]
    result = t.to_jsonl(articles)
    lines = result.strip().split("\n")
    assert len(lines) == 3


def test_data_transformer_no_metadata():
    cfg = TransformerConfig(include_metadata=False)
    t = DataTransformer(config=cfg)
    data = t.transform(ARTICLE)
    assert "metadata" not in data
