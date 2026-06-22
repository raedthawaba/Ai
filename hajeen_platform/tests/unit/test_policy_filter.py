"""Tests for PolicyFilter — section 5.8."""
from __future__ import annotations
import pytest
from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.filtering.policy_filter import (
    PolicyFilter, PolicyFilterConfig, PolicyResult
)
from shared.utils.datetime_utils import utc_now

def _make_article(
    content: str = "This is a sufficiently long article content for testing purposes.",
    url: str = "https://example.com/article",
    title: str = "Test Article",
    aid: str = "art_001",
) -> Article:
    return Article(
        id=aid,
        title=title,
        content=content,
        url=url,
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test_channel", language="en"),
    )


class TestPolicyFilterConfig:
    def test_default_config(self):
        cfg = PolicyFilterConfig()
        assert cfg.min_content_length == 50
        assert cfg.blocked_domains == []
        assert cfg.blocked_keywords == []

    def test_from_yaml_missing_file(self):
        cfg = PolicyFilterConfig.from_yaml("nonexistent_path.yaml")
        assert isinstance(cfg, PolicyFilterConfig)

    def test_from_yaml_valid(self, tmp_path):
        yaml_content = """
policy_filter:
  blocked_domains:
    - spam.com
  blocked_keywords:
    - casino
  min_content_length: 100
"""
        f = tmp_path / "filters.yaml"
        f.write_text(yaml_content)
        cfg = PolicyFilterConfig.from_yaml(f)
        assert "spam.com" in cfg.blocked_domains
        assert "casino" in cfg.blocked_keywords
        assert cfg.min_content_length == 100


class TestPolicyFilter:
    def setup_method(self):
        self.cfg = PolicyFilterConfig(
            blocked_domains=["spam.com", "fake-news.net"],
            blocked_keywords=["casino", "gambling"],
            min_content_length=30,
        )
        self.pf = PolicyFilter(config=self.cfg)

    def test_passes_clean_article(self):
        art = _make_article()
        result = self.pf.check_article(art)
        assert result.passes is True
        assert result.rejection_reason is None

    def test_rejects_short_content(self):
        art = _make_article(content="Too short.")
        result = self.pf.check_article(art)
        assert result.passes is False
        assert "content_too_short" in result.rejection_reason

    def test_rejects_blocked_domain(self):
        art = _make_article(url="https://spam.com/article")
        result = self.pf.check_article(art)
        assert result.passes is False
        assert "blocked_domain" in result.rejection_reason

    def test_rejects_blocked_keyword_in_content(self):
        art = _make_article(content="Visit our casino for the best gambling experience online today!")
        result = self.pf.check_article(art)
        assert result.passes is False
        assert "blocked_keyword" in result.rejection_reason

    def test_rejects_blocked_keyword_in_title(self):
        art = _make_article(title="Win at casino tonight", content="A" * 50)
        result = self.pf.check_article(art)
        assert result.passes is False

    def test_filter_batch(self):
        articles = [
            _make_article(aid="a1"),
            _make_article(content="short", aid="a2"),
            _make_article(url="https://spam.com/art", aid="a3"),
        ]
        kept, results = self.pf.filter_batch(articles)
        assert len(kept) == 1
        assert kept[0].id == "a1"
        assert len(results) == 3

    def test_blacklist_domains_also_work(self):
        cfg = PolicyFilterConfig(
            blacklist_domains=["blacklisted.org"],
            min_content_length=1,
        )
        pf = PolicyFilter(config=cfg)
        art = _make_article(url="https://blacklisted.org/news")
        result = pf.check_article(art)
        assert result.passes is False

    def test_case_insensitive_by_default(self):
        cfg = PolicyFilterConfig(
            blocked_keywords=["CASINO"],
            min_content_length=10,
            case_sensitive=False,
        )
        pf = PolicyFilter(config=cfg)
        art = _make_article(content="Visit our casino tonight and enjoy!")
        result = pf.check_article(art)
        assert result.passes is False
