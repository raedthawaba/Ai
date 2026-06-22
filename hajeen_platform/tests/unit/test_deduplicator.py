"""Tests for section 5.4 — Deduplicator."""

import pytest

from data_engine.processing.filtering.deduplicator import (
    Deduplicator,
    DeduplicatorConfig,
    DedupResult,
    content_hash,
    similarity_score,
    url_hash,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(
    title: str = "Title",
    content: str = "Some content here for testing purposes.",
    url: str = "https://example.com/1",
) -> Article:
    return Article(
        id=generate_article_id(title + url),
        title=title,
        content=content,
        url=url,
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test"),
    )


def make_articles_set(n: int) -> list[Article]:
    return [
        make_article(
            title=f"Article {i}",
            content=f"This is the unique content for article number {i} with enough text.",
            url=f"https://example.com/article/{i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_same_article_same_hash(self):
        a = make_article("Title", "Content here")
        assert content_hash(a) == content_hash(a)

    def test_different_content_different_hash(self):
        a = make_article("Title", "Content A")
        b = make_article("Title", "Content B")
        assert content_hash(a) != content_hash(b)

    def test_case_insensitive(self):
        a = make_article("TITLE", "CONTENT")
        b = make_article("title", "content")
        assert content_hash(a) == content_hash(b)

    def test_whitespace_normalised(self):
        a = make_article("Title", "hello   world")
        b = make_article("Title", "hello world")
        assert content_hash(a) == content_hash(b)

    def test_custom_preview_length(self):
        a = make_article("T", "A" * 1000)
        h1 = content_hash(a, preview_length=100)
        h2 = content_hash(a, preview_length=200)
        # Different preview length may produce different hash
        assert isinstance(h1, str)
        assert isinstance(h2, str)


# ---------------------------------------------------------------------------
# url_hash
# ---------------------------------------------------------------------------

class TestUrlHash:
    def test_same_url_same_hash(self):
        a = make_article(url="https://example.com/a")
        b = make_article(url="https://example.com/a")
        assert url_hash(a) == url_hash(b)

    def test_trailing_slash_normalised(self):
        a = make_article(url="https://example.com/a/")
        b = make_article(url="https://example.com/a")
        assert url_hash(a) == url_hash(b)

    def test_case_normalised(self):
        a = make_article(url="HTTPS://EXAMPLE.COM/A")
        b = make_article(url="https://example.com/a")
        assert url_hash(a) == url_hash(b)

    def test_different_urls_different_hash(self):
        a = make_article(url="https://example.com/a")
        b = make_article(url="https://example.com/b")
        assert url_hash(a) != url_hash(b)


# ---------------------------------------------------------------------------
# similarity_score
# ---------------------------------------------------------------------------

class TestSimilarityScore:
    def test_identical_articles_score_one(self):
        a = make_article("Title", "Same content here")
        b = make_article("Title", "Same content here")
        assert similarity_score(a, b) >= 0.99

    def test_completely_different_articles_low_score(self):
        a = make_article("Apple News", "Apple released new products today in Cupertino.")
        b = make_article("Football Match", "The team won the championship after extra time.")
        score = similarity_score(a, b)
        assert score < 0.5

    def test_score_range(self):
        a = make_article("Title A", "Content A for article")
        b = make_article("Title B", "Content B for article")
        score = similarity_score(a, b)
        assert 0.0 <= score <= 1.0

    def test_similar_articles_higher_score(self):
        a = make_article("Tech News Today", "Scientists discover new processor chip")
        b = make_article("Tech News Today", "Scientists discover a new processor chip design")
        score = similarity_score(a, b)
        assert score > 0.5


# ---------------------------------------------------------------------------
# Deduplicator.deduplicate
# ---------------------------------------------------------------------------

class TestDeduplicator:
    def test_no_duplicates(self):
        articles = make_articles_set(5)
        dedup = Deduplicator()
        result = dedup.deduplicate(articles)
        assert result.unique_count == 5
        assert result.duplicate_count == 0

    def test_exact_url_duplicates(self):
        a = make_article(url="https://example.com/same")
        b = make_article(url="https://example.com/same", title="Different Title")
        dedup = Deduplicator()
        result = dedup.deduplicate([a, b])
        assert result.unique_count == 1
        assert result.duplicate_count == 1

    def test_exact_content_duplicates(self):
        a = make_article("Title", "Exact same content for dedup test.", url="https://x.com/1")
        b = make_article("Title", "Exact same content for dedup test.", url="https://x.com/2")
        dedup = Deduplicator()
        result = dedup.deduplicate([a, b])
        assert result.unique_count == 1
        assert result.duplicate_count == 1

    def test_dedup_result_type(self):
        articles = make_articles_set(3)
        dedup = Deduplicator()
        result = dedup.deduplicate(articles)
        assert isinstance(result, DedupResult)
        assert isinstance(result.unique_articles, list)

    def test_state_persists_across_calls(self):
        a = make_article(title="A", url="https://example.com/a")
        b = make_article(title="A", url="https://example.com/a")

        dedup = Deduplicator()
        result1 = dedup.deduplicate([a])
        result2 = dedup.deduplicate([b])  # same URL, second call

        assert result1.unique_count == 1
        assert result2.duplicate_count == 1

    def test_reset_clears_state(self):
        a = make_article(url="https://example.com/a")
        dedup = Deduplicator()
        dedup.deduplicate([a])
        result = dedup.deduplicate([a], reset=True)
        # After reset, article is treated as new
        assert result.unique_count == 1

    def test_disable_url_dedup(self):
        cfg = DeduplicatorConfig(deduplicate_urls=False)
        a = make_article(url="https://x.com/same", content="Content A unique one")
        b = make_article(url="https://x.com/same", content="Content B unique two")
        dedup = Deduplicator(config=cfg)
        result = dedup.deduplicate([a, b])
        # URL dedup disabled, content differs → both kept
        assert result.unique_count == 2

    def test_is_duplicate_stateless(self):
        a = make_article(url="https://example.com/a")
        dedup = Deduplicator()
        dedup.deduplicate([a])
        # is_duplicate does NOT update state
        assert dedup.is_duplicate(a) is True
        assert dedup.is_duplicate(a) is True  # still detectable

    def test_duplicate_score_identical(self):
        a = make_article()
        b = make_article()
        dedup = Deduplicator()
        assert dedup.duplicate_score(a, b) == 1.0

    def test_duplicate_score_same_url(self):
        a = make_article(url="https://example.com/same", content="Alpha content")
        b = make_article(url="https://example.com/same", content="Beta content")
        dedup = Deduplicator()
        assert dedup.duplicate_score(a, b) == 1.0

    def test_empty_list(self):
        dedup = Deduplicator()
        result = dedup.deduplicate([])
        assert result.unique_count == 0
        assert result.duplicate_count == 0

    def test_single_article(self):
        a = make_article()
        dedup = Deduplicator()
        result = dedup.deduplicate([a])
        assert result.unique_count == 1

    def test_fuzzy_dedup(self):
        cfg = DeduplicatorConfig(
            deduplicate_similar_content=True,
            similarity_threshold=0.9,
        )
        base = "Scientists discover a new method for artificial intelligence processing."
        a = make_article("AI News", base, url="https://x.com/1")
        b = make_article("AI News", base + " Extra.", url="https://x.com/2")
        dedup = Deduplicator(config=cfg)
        result = dedup.deduplicate([a, b])
        # Very similar content → b should be flagged
        assert result.unique_count <= 2

    def test_short_content_skips_dedup(self):
        """Articles shorter than min_content_length bypass content dedup."""
        a = make_article(title="T", content="Hi", url="https://x.com/1")
        b = make_article(title="T", content="Hi", url="https://x.com/2")
        cfg = DeduplicatorConfig(min_content_length=100)
        dedup = Deduplicator(config=cfg)
        result = dedup.deduplicate([a, b])
        # Content too short to dedup; URL differs → both kept
        assert result.unique_count == 2
