"""Tests for TextChunker — section 5.12."""
from __future__ import annotations
import pytest
from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.transformation.chunker import (
    TextChunker, ChunkerConfig, Chunk,
    _split_paragraph, _split_sentence, _fixed_split,
    _merge_with_overlap, _estimate_tokens,
)
from shared.utils.datetime_utils import utc_now


LONG_TEXT = (
    "الفقرة الأولى تتحدث عن الذكاء الاصطناعي وتطبيقاته المتنوعة في الحياة اليومية.\n\n"
    "الفقرة الثانية تتناول التعلم الآلي وأساليب التدريب على البيانات الكبيرة.\n\n"
    "الفقرة الثالثة تستعرض تقنيات معالجة اللغات الطبيعية وفهم النصوص العربية.\n\n"
    "الفقرة الرابعة تتكلم عن أهمية جودة البيانات في بناء نماذج الذكاء الاصطناعي."
)

EN_TEXT = (
    "First paragraph about artificial intelligence and its impact on modern society.\n\n"
    "Second paragraph covering machine learning algorithms and neural networks.\n\n"
    "Third paragraph discussing natural language processing capabilities.\n\n"
    "Fourth paragraph examining data quality requirements for AI systems."
)


def _make_article(content: str) -> Article:
    return Article(
        id="chunk_001",
        title="Chunker Test",
        content=content,
        url="https://example.com/chunk",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test", language="ar"),
    )


class TestLowLevelHelpers:
    def test_split_paragraph(self):
        parts = _split_paragraph(LONG_TEXT)
        assert len(parts) >= 3

    def test_split_sentence(self):
        text = "First sentence. Second sentence! Third one?"
        parts = _split_sentence(text)
        assert len(parts) >= 2

    def test_fixed_split_no_overlap(self):
        text = "A" * 100
        parts = _fixed_split(text, chunk_size=30, overlap=0)
        assert len(parts) >= 3
        assert all(len(p) <= 30 for p in parts)

    def test_fixed_split_with_overlap(self):
        text = "A" * 100
        parts = _fixed_split(text, chunk_size=30, overlap=10)
        # With overlap, consecutive chunks should share suffix/prefix
        assert len(parts) >= 3

    def test_merge_with_overlap(self):
        parts = ["short one", "another one", "and another here", "final piece"]
        chunks = _merge_with_overlap(parts, max_chars=40, overlap_chars=10, min_length=5)
        assert len(chunks) >= 1

    def test_estimate_tokens(self):
        text = "A" * 400
        tokens = _estimate_tokens(text)
        assert tokens == 100  # 400 / 4


class TestTextChunker:
    def test_paragraph_strategy(self):
        cfg = ChunkerConfig(strategy="paragraph", chunk_size=500, overlap=50)
        chunker = TextChunker(config=cfg)
        chunks = chunker.chunk_text(LONG_TEXT)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_sentence_strategy(self):
        cfg = ChunkerConfig(strategy="sentence", chunk_size=200, overlap=30)
        chunker = TextChunker(config=cfg)
        chunks = chunker.chunk_text(EN_TEXT)
        assert len(chunks) >= 1

    def test_fixed_strategy(self):
        cfg = ChunkerConfig(strategy="fixed", chunk_size=100, overlap=20)
        chunker = TextChunker(config=cfg)
        chunks = chunker.chunk_text("X" * 500)
        assert len(chunks) >= 4

    def test_token_estimate_strategy(self):
        cfg = ChunkerConfig(strategy="token_estimate", chunk_size=50, overlap=10)
        chunker = TextChunker(config=cfg)
        chunks = chunker.chunk_text(EN_TEXT)
        assert len(chunks) >= 1

    def test_empty_text_returns_empty(self):
        chunker = TextChunker()
        assert chunker.chunk_text("") == []

    def test_chunk_has_valid_fields(self):
        chunker = TextChunker()
        chunks = chunker.chunk_text(EN_TEXT)
        for c in chunks:
            assert c.index >= 0
            assert len(c.text) > 0
            assert c.start_char >= 0
            assert c.end_char > c.start_char
            assert c.estimated_tokens > 0

    def test_max_chunks_config(self):
        cfg = ChunkerConfig(max_chunks=2)
        chunker = TextChunker(config=cfg)
        chunks = chunker.chunk_text(LONG_TEXT)
        assert len(chunks) <= 2

    def test_min_chunk_length_filter(self):
        cfg = ChunkerConfig(strategy="fixed", chunk_size=10, overlap=0, min_chunk_length=8)
        chunker = TextChunker(config=cfg)
        text = "Hello World! More text here to create multiple chunks."
        chunks = chunker.chunk_text(text)
        for c in chunks:
            assert len(c.text) >= 8

    def test_chunk_article(self):
        art = _make_article(LONG_TEXT)
        chunker = TextChunker()
        chunks = chunker.chunk_article(art)
        assert isinstance(chunks, list)

    def test_chunk_batch(self):
        arts = [_make_article(LONG_TEXT), _make_article(EN_TEXT)]
        chunker = TextChunker()
        results = chunker.chunk_batch(arts)
        assert len(results) == 2
        for art, chunks in results:
            assert isinstance(chunks, list)
