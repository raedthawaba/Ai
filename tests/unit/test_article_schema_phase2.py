"""Unit tests for Article schema Phase 2 additions."""
from __future__ import annotations

import json
import pytest
from datetime import datetime

from shared.schemas.article import (
    Article,
    ArticleMetadata,
    ArticleEntity,
    ProcessingState,
    generate_article_id,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(
    content: str = "This is a detailed article about technology and AI.",
    title: str = "Tech Article",
    language: str = "en",
    article_id: str | None = None,
) -> Article:
    return Article(
        id=article_id or generate_article_id(),
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=datetime(2024, 1, 1),
        metadata=ArticleMetadata(source_id="src_test", language=language),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_article_id
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateArticleId:
    def test_default_prefix(self):
        id_ = generate_article_id()
        assert id_.startswith("art_")

    def test_custom_prefix(self):
        id_ = generate_article_id(prefix="news")
        assert id_.startswith("news_")

    def test_unique_ids(self):
        ids = {generate_article_id() for _ in range(100)}
        assert len(ids) == 100

    def test_id_length_reasonable(self):
        id_ = generate_article_id()
        # "art_" + 8 hex chars = 12 chars
        assert len(id_) == 12


# ─────────────────────────────────────────────────────────────────────────────
# Tests: ProcessingState
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessingState:
    def test_default_state_is_raw(self):
        article = _make_article()
        assert article.processing_state == ProcessingState.RAW

    def test_state_can_be_set(self):
        article = _make_article()
        updated = article.model_copy(update={"processing_state": ProcessingState.CLEANED})
        assert updated.processing_state == ProcessingState.CLEANED

    def test_all_states_exist(self):
        states = {s.value for s in ProcessingState}
        assert "raw" in states
        assert "cleaned" in states
        assert "filtered" in states
        assert "enriched" in states
        assert "transformed" in states
        assert "failed" in states

    def test_state_is_string(self):
        # ProcessingState(str, Enum) يجب أن يكون قابلاً للمقارنة بـ str
        assert ProcessingState.RAW == "raw"
        assert ProcessingState.CLEANED == "cleaned"

    def test_state_serializes_in_dict(self):
        article = _make_article()
        d = article.to_dict()
        assert "processing_state" in d
        assert d["processing_state"] == "raw"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: content_hash
# ─────────────────────────────────────────────────────────────────────────────

class TestContentHash:
    def test_hash_is_64_hex_chars(self):
        article = _make_article()
        h = article.content_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_content_same_hash(self):
        a1 = _make_article(content="Same content here.", title="Same title")
        a2 = _make_article(content="Same content here.", title="Same title")
        assert a1.content_hash() == a2.content_hash()

    def test_different_content_different_hash(self):
        a1 = _make_article(content="First article content.", title="Title One")
        a2 = _make_article(content="Second article content.", title="Title Two")
        assert a1.content_hash() != a2.content_hash()

    def test_short_hash_is_16_chars(self):
        article = _make_article()
        short = article.short_hash()
        assert len(short) == 16

    def test_short_hash_is_prefix_of_full_hash(self):
        article = _make_article()
        full = article.content_hash()
        short = article.short_hash()
        assert full.startswith(short)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_dict
# ─────────────────────────────────────────────────────────────────────────────

class TestToDict:
    def test_to_dict_has_required_fields(self):
        article = _make_article()
        d = article.to_dict()
        assert "id" in d
        assert "title" in d
        assert "content" in d
        assert "url" in d
        assert "published_at" in d
        assert "metadata" in d
        assert "processing_state" in d

    def test_to_dict_excludes_content(self):
        article = _make_article()
        d = article.to_dict(exclude_content=True)
        assert "content" not in d
        assert "title" in d

    def test_to_dict_is_serializable(self):
        article = _make_article()
        d = article.to_dict()
        # يجب أن يكون قابلاً للـ JSON serialization
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_json / to_jsonl
# ─────────────────────────────────────────────────────────────────────────────

class TestToJson:
    def test_to_json_is_valid_json(self):
        article = _make_article()
        json_str = article.to_json()
        parsed = json.loads(json_str)
        assert parsed["id"] == article.id
        assert parsed["title"] == article.title

    def test_to_json_with_indent(self):
        article = _make_article()
        json_str = article.to_json(indent=2)
        assert "\n" in json_str  # indented JSON has newlines

    def test_to_jsonl_is_single_line(self):
        article = _make_article()
        jsonl = article.to_jsonl()
        assert "\n" not in jsonl

    def test_to_jsonl_is_valid_json(self):
        article = _make_article()
        jsonl = article.to_jsonl()
        parsed = json.loads(jsonl)
        assert parsed["id"] == article.id

    def test_to_jsonl_arabic_content(self):
        article = _make_article(
            content="هذا محتوى عربي مهم جداً",
            title="مقال عربي",
            language="ar",
        )
        jsonl = article.to_jsonl()
        parsed = json.loads(jsonl)
        assert "هذا محتوى عربي" in parsed["content"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Article.create factory method
# ─────────────────────────────────────────────────────────────────────────────

class TestArticleCreate:
    def test_create_with_auto_id(self):
        article = Article.create(
            title="Test Article",
            content="Test content for article.",
            url="https://example.com/test",
            published_at=datetime(2024, 1, 1),
            source_id="src_test",
        )
        assert article.id.startswith("art_")
        assert article.title == "Test Article"

    def test_create_with_custom_id(self):
        article = Article.create(
            title="Custom ID Article",
            content="Some content here.",
            url="https://example.com/test",
            published_at=datetime(2024, 1, 1),
            source_id="src_test",
            id="custom_001",
        )
        assert article.id == "custom_001"

    def test_create_default_language_arabic(self):
        article = Article.create(
            title="Arabic Article",
            content="محتوى عربي",
            url="https://example.com/test",
            published_at=datetime(2024, 1, 1),
            source_id="src_test",
        )
        assert article.metadata.language == "ar"

    def test_create_with_english_language(self):
        article = Article.create(
            title="English Article",
            content="English content here.",
            url="https://example.com/test",
            published_at=datetime(2024, 1, 1),
            source_id="src_test",
            language="en",
        )
        assert article.metadata.language == "en"

    def test_create_processing_state_is_raw(self):
        article = Article.create(
            title="New Article",
            content="Content here.",
            url="https://example.com/test",
            published_at=datetime(2024, 1, 1),
            source_id="src_test",
        )
        assert article.processing_state == ProcessingState.RAW
