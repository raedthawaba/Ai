"""Tests for TextCleaner — section 4.10."""

from __future__ import annotations

import pytest

from data_engine.processing.cleaning.text_cleaner import (
    CleanerConfig,
    TextCleaner,
    clean_text,
    decode_html_entities,
    fix_whitespace,
    normalize_alef,
    normalize_ta_marbuta,
    normalize_unicode,
    remove_emails,
    remove_harakat,
    remove_tatweel,
    remove_urls,
    strip_html,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(title: str, content: str, language: str = "ar") -> Article:
    return Article(
        id=generate_article_id(title),
        title=title,
        content=content,
        url="https://example.com/art",  # type: ignore[arg-type]
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test", language=language),
    )


# ---------------------------------------------------------------------------
# strip_html
# ---------------------------------------------------------------------------

def test_strip_html_removes_tags():
    result = strip_html("<p>Hello <b>World</b></p>")
    assert "<p>" not in result
    assert "<b>" not in result
    assert "Hello" in result
    assert "World" in result


def test_strip_html_empty():
    assert strip_html("") == ""


def test_strip_html_no_tags():
    assert strip_html("plain text") == "plain text"


def test_strip_html_self_closing():
    result = strip_html("line1<br/>line2")
    assert "line1" in result
    assert "line2" in result
    assert "<br" not in result


# ---------------------------------------------------------------------------
# decode_html_entities
# ---------------------------------------------------------------------------

def test_decode_html_entities_amp():
    assert "&amp;" not in decode_html_entities("Tom &amp; Jerry")
    assert "Tom & Jerry" == decode_html_entities("Tom &amp; Jerry")


def test_decode_html_entities_lt_gt():
    result = decode_html_entities("&lt;div&gt;")
    assert "<div>" == result


def test_decode_html_entities_nbsp():
    result = decode_html_entities("word&nbsp;word")
    assert "&nbsp;" not in result


# ---------------------------------------------------------------------------
# remove_urls
# ---------------------------------------------------------------------------

def test_remove_urls_http():
    assert "https://example.com" not in remove_urls("Visit https://example.com today.")


def test_remove_urls_www():
    assert "www.example.com" not in remove_urls("Go to www.example.com for more.")


def test_remove_urls_preserves_surrounding_text():
    result = remove_urls("Read more at https://example.com for details.")
    assert "Read more at" in result
    assert "for details" in result


# ---------------------------------------------------------------------------
# remove_emails
# ---------------------------------------------------------------------------

def test_remove_emails():
    result = remove_emails("Contact user@example.com for help.")
    assert "user@example.com" not in result
    assert "Contact" in result


def test_remove_emails_no_email():
    text = "No email here."
    assert remove_emails(text) == text


# ---------------------------------------------------------------------------
# remove_harakat
# ---------------------------------------------------------------------------

def test_remove_harakat_basic():
    text = "مُحَمَّد"
    result = remove_harakat(text)
    assert result == "محمد"


def test_remove_harakat_no_harakat():
    text = "محمد"
    assert remove_harakat(text) == "محمد"


def test_remove_harakat_full_sentence():
    text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
    result = remove_harakat(text)
    assert "بسم" in result
    assert "ِ" not in result


# ---------------------------------------------------------------------------
# remove_tatweel
# ---------------------------------------------------------------------------

def test_remove_tatweel():
    text = "جميـــل"
    result = remove_tatweel(text)
    assert "\u0640" not in result
    assert "جميل" == result


def test_remove_tatweel_no_tatweel():
    text = "جميل"
    assert remove_tatweel(text) == "جميل"


# ---------------------------------------------------------------------------
# normalize_alef
# ---------------------------------------------------------------------------

def test_normalize_alef_variants():
    assert normalize_alef("أحمد") == "احمد"
    assert normalize_alef("إبراهيم") == "ابراهيم"
    assert normalize_alef("آدم") == "ادم"


def test_normalize_alef_plain_alef_unchanged():
    assert normalize_alef("اكاديمية") == "اكاديمية"


# ---------------------------------------------------------------------------
# normalize_ta_marbuta
# ---------------------------------------------------------------------------

def test_normalize_ta_marbuta():
    assert normalize_ta_marbuta("مدرسة") == "مدرسه"
    assert normalize_ta_marbuta("جامعة") == "جامعه"


def test_normalize_ta_marbuta_no_change():
    assert normalize_ta_marbuta("محمد") == "محمد"


# ---------------------------------------------------------------------------
# fix_whitespace
# ---------------------------------------------------------------------------

def test_fix_whitespace_multiple_spaces():
    assert fix_whitespace("hello   world") == "hello world"


def test_fix_whitespace_tabs():
    assert fix_whitespace("hello\t\tworld") == "hello world"


def test_fix_whitespace_leading_trailing():
    assert fix_whitespace("  hello  ") == "hello"


def test_fix_whitespace_multiple_newlines():
    result = fix_whitespace("para1\n\n\n\npara2")
    assert result == "para1\n\npara2"


def test_fix_whitespace_empty():
    assert fix_whitespace("") == ""


# ---------------------------------------------------------------------------
# clean_text (pipeline)
# ---------------------------------------------------------------------------

def test_clean_text_arabic_full():
    text = "<p>مُحَمَّدٌ يَعْمَلُ بِجِدٍّ كَبِيرٍ</p>"
    result = clean_text(text)
    assert "<p>" not in result
    assert "ُ" not in result
    assert "َ" not in result
    assert "محمد" in result


def test_clean_text_html_and_url():
    text = '<a href="https://example.com">اقرا المزيد</a>'
    result = clean_text(text)
    assert "<a" not in result
    assert "https://" not in result
    assert "اقرا المزيد" in result


def test_clean_text_empty():
    assert clean_text("") == ""


def test_clean_text_config_disable_url_removal():
    cfg = CleanerConfig(remove_urls=False)
    text = "Visit https://example.com"
    result = clean_text(text, cfg)
    assert "https://example.com" in result


def test_clean_text_config_remove_mentions():
    cfg = CleanerConfig(remove_mentions=True)
    text = "Thanks @user for the info."
    result = clean_text(text, cfg)
    assert "@user" not in result


def test_clean_text_config_remove_hashtags():
    cfg = CleanerConfig(remove_hashtags=True)
    text = "Trending #Python today."
    result = clean_text(text, cfg)
    assert "#Python" not in result


# ---------------------------------------------------------------------------
# TextCleaner (article-level)
# ---------------------------------------------------------------------------

def test_text_cleaner_clean_article():
    article = _make_article(
        title="مُحَمَّدٌ <b>يَكْتُبُ</b>",
        content="<p>النَّصُّ الأَصْلِيُّ لِلْمَقَالَةِ https://link.com</p>",
    )
    cleaner = TextCleaner()
    cleaned = cleaner.clean_article(article)
    assert "<b>" not in cleaned.title
    assert "<p>" not in cleaned.content
    assert "https://" not in cleaned.content
    assert "ُ" not in cleaned.title
    assert cleaned.id == article.id


def test_text_cleaner_does_not_mutate_original():
    article = _make_article(
        title="مُحَمَّد",
        content="<p>محتوى</p>",
    )
    cleaner = TextCleaner()
    cleaned = cleaner.clean_article(article)
    assert article.title == "مُحَمَّد"
    assert cleaned.title == "محمد"


def test_text_cleaner_clean_batch():
    articles = [
        _make_article(f"عنوان {i} <b>bold</b>", f"محتوى {i} رابط https://x.com")
        for i in range(5)
    ]
    cleaner = TextCleaner()
    result = cleaner.clean_batch(articles)
    assert len(result) == 5
    for a in result:
        assert "<b>" not in a.title
        assert "https://" not in a.content


def test_text_cleaner_preserves_summary():
    article = _make_article("عنوان", "محتوى")
    article = article.model_copy(update={"summary": "ملخص <b>جيد</b>"})
    cleaner = TextCleaner()
    cleaned = cleaner.clean_article(article)
    assert "<b>" not in (cleaned.summary or "")


def test_text_cleaner_english_content():
    article = _make_article(
        title="Breaking News",
        content="<p>Read more at https://news.com. Contact info@news.com</p>",
        language="en",
    )
    cleaner = TextCleaner()
    cleaned = cleaner.clean_article(article)
    assert "<p>" not in cleaned.content
    assert "https://" not in cleaned.content
    assert "info@news.com" not in cleaned.content
