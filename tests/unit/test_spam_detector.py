"""Tests for section 5.7 — Spam Detector."""

import pytest

from data_engine.processing.filtering.spam_detector import (
    SpamDetector,
    SpamDetectorConfig,
    SpamResult,
    check_caps_ratio,
    check_keyword_spam,
    check_punct_density,
    check_repeated_links,
    check_repeated_phrases,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(
    title: str = "Test",
    content: str = "Normal content.",
    url: str = "https://example.com/1",
) -> Article:
    return Article(
        id=generate_article_id(title + url),
        title=title,
        content=content,
        url=url,
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test", language="en"),
    )


CLEAN_CONTENT = (
    "Scientists have announced a breakthrough in renewable energy technology. "
    "The new solar panels are 40 percent more efficient than existing models. "
    "This development could significantly reduce carbon emissions globally."
)

SPAM_KEYWORD_CONTENT = (
    "Buy now! Click here for the best price! Limited time exclusive deal! "
    "Buy now click here discount sale buy now click here! "
    "Free offer guaranteed! Buy now click here buy now!"
)

REPEATED_LINK_CONTENT = (
    "Visit https://spam.example.com/offer for amazing deals. "
    "Also see https://spam.example.com/offer again. "
    "And once more https://spam.example.com/offer is great. "
    "Check https://spam.example.com/offer out. "
    "https://spam.example.com/offer is the best!"
)

REPEATED_PHRASE_CONTENT = " ".join(
    ["buy this product today at discount price"] * 15
)

CAPS_CONTENT = "BUY NOW CLICK HERE LIMITED TIME OFFER FREE DISCOUNT SALE WIN PRIZE"

PUNCT_CONTENT = "Amazing offer!!! Click now??? Buy today!!!! Wow??? Really!!!"

ARABIC_SPAM = (
    "اشترِ الآن! اشترِ الآن! خصم كبير جداً! اشترِ الآن! انقر هنا! "
    "فرصة ذهبية اشترِ الآن! لا تفوتها اشترِ الآن!"
)


# ---------------------------------------------------------------------------
# check_keyword_spam
# ---------------------------------------------------------------------------

class TestCheckKeywordSpam:
    def test_detects_spam_keywords(self):
        is_spam, density, kw = check_keyword_spam(SPAM_KEYWORD_CONTENT)
        assert is_spam is True
        assert density > 0.0

    def test_clean_text_not_spam(self):
        is_spam, density, kw = check_keyword_spam(CLEAN_CONTENT)
        assert is_spam is False

    def test_custom_keywords(self):
        is_spam, density, kw = check_keyword_spam(
            "This article is about custom spam word here.",
            custom_keywords=["custom spam word"],
        )
        assert is_spam is True

    def test_empty_text_not_spam(self):
        is_spam, density, _ = check_keyword_spam("")
        assert is_spam is False
        assert density == 0.0

    def test_arabic_spam_keywords(self):
        is_spam, density, kw = check_keyword_spam(ARABIC_SPAM)
        assert is_spam is True

    def test_returns_matched_keyword(self):
        _, _, kw = check_keyword_spam(SPAM_KEYWORD_CONTENT)
        assert len(kw) > 0


# ---------------------------------------------------------------------------
# check_repeated_links
# ---------------------------------------------------------------------------

class TestCheckRepeatedLinks:
    def test_detects_repeated_links(self):
        is_spam, count, url = check_repeated_links(REPEATED_LINK_CONTENT, max_repeats=3)
        assert is_spam is True
        assert count >= 4

    def test_single_link_not_spam(self):
        text = "Visit https://example.com for info."
        is_spam, count, _ = check_repeated_links(text)
        assert is_spam is False

    def test_no_links(self):
        is_spam, count, url = check_repeated_links(CLEAN_CONTENT)
        assert is_spam is False
        assert count == 0
        assert url == ""

    def test_different_links_not_spam(self):
        text = (
            "https://a.com https://b.com https://c.com "
            "https://d.com https://e.com"
        )
        is_spam, count, _ = check_repeated_links(text, max_repeats=3)
        assert is_spam is False

    def test_returns_repeated_url(self):
        _, _, url = check_repeated_links(REPEATED_LINK_CONTENT, max_repeats=3)
        assert "spam.example.com" in url


# ---------------------------------------------------------------------------
# check_repeated_phrases
# ---------------------------------------------------------------------------

class TestCheckRepeatedPhrases:
    def test_detects_repeated_phrases(self):
        is_spam, ratio = check_repeated_phrases(REPEATED_PHRASE_CONTENT, max_ratio=0.3)
        assert is_spam is True
        assert ratio > 0.3

    def test_clean_text_not_spam(self):
        is_spam, ratio = check_repeated_phrases(CLEAN_CONTENT)
        assert is_spam is False

    def test_short_text_not_spam(self):
        is_spam, ratio = check_repeated_phrases("Hi there")
        assert is_spam is False

    def test_ratio_range(self):
        _, ratio = check_repeated_phrases(CLEAN_CONTENT)
        assert 0.0 <= ratio <= 1.0


# ---------------------------------------------------------------------------
# check_caps_ratio
# ---------------------------------------------------------------------------

class TestCheckCapsRatio:
    def test_detects_excessive_caps(self):
        is_spam, ratio = check_caps_ratio(CAPS_CONTENT, max_ratio=0.5)
        assert is_spam is True
        assert ratio > 0.5

    def test_normal_text_not_caps_spam(self):
        is_spam, ratio = check_caps_ratio(CLEAN_CONTENT)
        assert is_spam is False

    def test_arabic_text_ignored(self):
        """Arabic chars are not classified as CAPS → not spam."""
        is_spam, ratio = check_caps_ratio(ARABIC_SPAM)
        assert is_spam is False

    def test_empty_text(self):
        is_spam, ratio = check_caps_ratio("")
        assert is_spam is False
        assert ratio == 0.0

    def test_ratio_range(self):
        _, ratio = check_caps_ratio(CLEAN_CONTENT)
        assert 0.0 <= ratio <= 1.0


# ---------------------------------------------------------------------------
# check_punct_density
# ---------------------------------------------------------------------------

class TestCheckPunctDensity:
    def test_detects_excessive_punct(self):
        is_spam, density = check_punct_density(PUNCT_CONTENT, max_density=0.05)
        assert is_spam is True

    def test_clean_text_not_spam(self):
        is_spam, density = check_punct_density(CLEAN_CONTENT)
        assert is_spam is False

    def test_empty_text(self):
        is_spam, density = check_punct_density("")
        assert is_spam is False
        assert density == 0.0


# ---------------------------------------------------------------------------
# SpamDetector
# ---------------------------------------------------------------------------

class TestSpamDetector:
    def test_clean_article_not_spam(self):
        article = make_article(title="AI Research", content=CLEAN_CONTENT)
        detector = SpamDetector()
        result = detector.detect(article)
        assert isinstance(result, SpamResult)
        assert result.is_spam is False

    def test_spam_keywords_detected(self):
        article = make_article(title="Deal!", content=SPAM_KEYWORD_CONTENT)
        detector = SpamDetector()
        result = detector.detect(article)
        assert result.is_spam is True
        assert "keyword_spam" in result.triggered_rules

    def test_repeated_links_detected(self):
        article = make_article(content=REPEATED_LINK_CONTENT)
        cfg = SpamDetectorConfig(max_repeated_links=3)
        detector = SpamDetector(config=cfg)
        result = detector.detect(article)
        assert "repeated_links" in result.triggered_rules

    def test_repeated_phrases_detected(self):
        article = make_article(content=REPEATED_PHRASE_CONTENT)
        cfg = SpamDetectorConfig(max_phrase_repeat_ratio=0.2)
        detector = SpamDetector(config=cfg)
        result = detector.detect(article)
        assert "repeated_phrases" in result.triggered_rules

    def test_caps_detected(self):
        article = make_article(title="DEAL", content=CAPS_CONTENT)
        cfg = SpamDetectorConfig(max_caps_ratio=0.3)
        detector = SpamDetector(config=cfg)
        result = detector.detect(article)
        assert "caps_ratio" in result.triggered_rules

    def test_punct_detected(self):
        article = make_article(content=PUNCT_CONTENT)
        cfg = SpamDetectorConfig(max_punct_density=0.02)
        detector = SpamDetector(config=cfg)
        result = detector.detect(article)
        assert "punct_density" in result.triggered_rules

    def test_arabic_spam_detected(self):
        article = make_article(title="عرض", content=ARABIC_SPAM)
        detector = SpamDetector()
        result = detector.detect(article)
        assert result.is_spam is True

    def test_spam_score_range(self):
        article = make_article(content=SPAM_KEYWORD_CONTENT)
        detector = SpamDetector()
        result = detector.detect(article)
        assert 0.0 <= result.spam_score <= 1.0

    def test_spam_score_zero_for_clean(self):
        article = make_article(content=CLEAN_CONTENT)
        detector = SpamDetector()
        result = detector.detect(article)
        assert result.spam_score == 0.0

    def test_custom_keywords(self):
        cfg = SpamDetectorConfig(custom_keywords=["custom spam phrase"])
        article = make_article(
            content="This article contains custom spam phrase multiple times. "
                    "custom spam phrase is here. custom spam phrase again."
        )
        detector = SpamDetector(config=cfg)
        result = detector.detect(article)
        assert result.is_spam is True

    def test_result_has_rule_details(self):
        article = make_article(content=SPAM_KEYWORD_CONTENT)
        detector = SpamDetector()
        result = detector.detect(article)
        assert "keyword_density" in result.rule_details

    def test_filter_batch(self):
        articles = [
            make_article("Clean", CLEAN_CONTENT, url="https://x.com/1"),
            make_article("Spam", SPAM_KEYWORD_CONTENT, url="https://x.com/2"),
        ]
        detector = SpamDetector()
        clean, results = detector.filter_batch(articles)
        assert len(results) == 2
        assert len(clean) >= 1

    def test_filter_batch_empty(self):
        detector = SpamDetector()
        clean, results = detector.filter_batch([])
        assert clean == []
        assert results == []

    def test_disabled_rules(self):
        cfg = SpamDetectorConfig(enabled_rules=[])
        article = make_article(content=SPAM_KEYWORD_CONTENT)
        detector = SpamDetector(config=cfg)
        result = detector.detect(article)
        assert result.is_spam is False   # no rules → no spam

    def test_spam_result_str(self):
        article = make_article(content=SPAM_KEYWORD_CONTENT)
        detector = SpamDetector()
        result = detector.detect(article)
        s = str(result)
        assert "SpamResult" in s
