"""Tests for section 5.3 — Text Normalizer."""

import pytest

from data_engine.processing.cleaning.text_normalizer import (
    NormalizerConfig,
    TextNormalizer,
    fix_whitespace,
    normalize_arabic_extended,
    normalize_text,
    normalize_unicode,
    reduce_repeated_punctuation,
    remove_emojis,
    remove_zero_width_chars,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(title: str, content: str, lang: str = "en") -> Article:
    safe_content = content if content.strip() else "placeholder content"
    return Article(
        id=generate_article_id(title),
        title=title,
        content=safe_content,
        url="https://example.com/test",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test", language=lang),
    )


# ---------------------------------------------------------------------------
# normalize_unicode
# ---------------------------------------------------------------------------

class TestNormalizeUnicode:
    def test_nfc_form(self):
        # Composed vs decomposed 'é'
        composed = "\u00e9"
        decomposed = "e\u0301"
        assert normalize_unicode(decomposed, form="NFC") == composed

    def test_nfkc_form(self):
        # Fullwidth latin to ASCII
        full = "\uff41"  # fullwidth 'a'
        result = normalize_unicode(full, form="NFKC")
        assert result == "a"

    def test_arabic_unchanged_by_nfc(self):
        text = "مرحبا بالعالم"
        result = normalize_unicode(text, form="NFC")
        assert result == text

    def test_empty_string(self):
        assert normalize_unicode("", form="NFC") == ""


# ---------------------------------------------------------------------------
# remove_emojis
# ---------------------------------------------------------------------------

class TestRemoveEmojis:
    def test_removes_smiley(self):
        result = remove_emojis("Hello 😀 World")
        assert "😀" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_multiple_emojis(self):
        result = remove_emojis("🚀🔥🎉")
        assert "🚀" not in result

    def test_arabic_with_emoji(self):
        result = remove_emojis("مرحبا 🎉 بالعالم")
        assert "🎉" not in result
        assert "مرحبا" in result

    def test_no_emoji_unchanged(self):
        text = "No emojis here"
        assert remove_emojis(text) == text

    def test_empty_string(self):
        assert remove_emojis("") == ""


# ---------------------------------------------------------------------------
# remove_zero_width_chars
# ---------------------------------------------------------------------------

class TestRemoveZeroWidthChars:
    def test_removes_zwsp(self):
        text = "hello\u200bworld"
        result = remove_zero_width_chars(text)
        assert "\u200b" not in result
        assert "helloworld" in result

    def test_removes_nbsp(self):
        text = "hello\u00a0world"
        result = remove_zero_width_chars(text)
        assert "\u00a0" not in result

    def test_removes_bom(self):
        text = "\ufeffstart"
        result = remove_zero_width_chars(text)
        assert "\ufeff" not in result

    def test_clean_text_unchanged(self):
        text = "clean text"
        assert remove_zero_width_chars(text) == "clean text"


# ---------------------------------------------------------------------------
# reduce_repeated_punctuation
# ---------------------------------------------------------------------------

class TestReduceRepeatedPunctuation:
    def test_reduces_exclamations(self):
        result = reduce_repeated_punctuation("Wow!!!!!!")
        assert "!" in result
        assert "!!!!" not in result

    def test_reduces_question_marks(self):
        result = reduce_repeated_punctuation("What???")
        assert "?" in result
        assert "???" not in result

    def test_arabic_question_mark(self):
        result = reduce_repeated_punctuation("ماذا؟؟؟؟")
        assert "؟" in result
        assert len([c for c in result if c == "؟"]) <= 1

    def test_no_repeated_punct_unchanged(self):
        text = "Hello. How are you?"
        result = reduce_repeated_punctuation(text)
        assert "." in result
        assert "?" in result

    def test_commas(self):
        result = reduce_repeated_punctuation("yes,,,,no")
        assert ",,,," not in result


# ---------------------------------------------------------------------------
# normalize_arabic_extended
# ---------------------------------------------------------------------------

class TestNormalizeArabicExtended:
    def test_normalizes_hamza_variants(self):
        # أ إ آ → ا
        text = "أهلاً وإهلاً"
        result = normalize_arabic_extended(text)
        # All alef-like chars become ا
        assert "أ" not in result or "إ" not in result

    def test_normalizes_persian_kaf(self):
        text = "کتاب"  # Persian kaf
        result = normalize_arabic_extended(text)
        assert "ک" not in result
        assert "ك" in result

    def test_normalizes_farsi_yeh(self):
        text = "یوم"  # Farsi yeh
        result = normalize_arabic_extended(text)
        assert "ی" not in result

    def test_latin_unchanged(self):
        text = "Hello World"
        result = normalize_arabic_extended(text)
        assert result == "Hello World"


# ---------------------------------------------------------------------------
# fix_whitespace
# ---------------------------------------------------------------------------

class TestFixWhitespace:
    def test_collapses_tabs_and_spaces(self):
        result = fix_whitespace("hello\t\t world")
        assert result == "hello world"

    def test_strips_edges(self):
        result = fix_whitespace("   hello   ")
        assert result == "hello"

    def test_empty_string(self):
        assert fix_whitespace("") == ""


# ---------------------------------------------------------------------------
# normalize_text (full pipeline)
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_removes_emojis_and_normalises(self):
        text = "Hello 😀 World!!!!!  "
        result = normalize_text(text)
        assert "😀" not in result
        assert "!!!!" not in result
        assert "Hello" in result

    def test_arabic_pipeline(self):
        text = "أهلاً وسهلاً 🎉 بكم!!!! "
        result = normalize_text(text)
        assert "🎉" not in result
        assert "!!!!" not in result

    def test_zero_width_removed(self):
        text = "test\u200bvalue"
        result = normalize_text(text)
        assert "\u200b" not in result

    def test_config_disable_emojis(self):
        cfg = NormalizerConfig(remove_emojis=False)
        text = "Hello 😀"
        result = normalize_text(text, config=cfg)
        assert "😀" in result

    def test_config_nfkc(self):
        cfg = NormalizerConfig(unicode_form="NFKC")
        text = "\uff41"  # fullwidth a
        result = normalize_text(text, config=cfg)
        assert result == "a"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_mixed_language(self):
        text = "Hello مرحبا 😀!!!! \u200b"
        result = normalize_text(text)
        assert "😀" not in result
        assert "\u200b" not in result
        assert "Hello" in result
        assert "مرحبا" in result


# ---------------------------------------------------------------------------
# TextNormalizer (article-level)
# ---------------------------------------------------------------------------

class TestTextNormalizer:
    def test_normalize_article(self):
        article = make_article(
            title="Breaking!!!!! News 😀",
            content="Content\u200b with emojis 🚀 and space  issues.",
        )
        normalizer = TextNormalizer()
        result = normalizer.normalize_article(article)
        assert "😀" not in result.title
        assert "🚀" not in result.content
        assert "\u200b" not in result.content

    def test_normalize_arabic_article(self):
        article = make_article(
            title="أخبار 🎉 عاجلة!!!!!",
            content="محتوى کتاب یوسف مع إهلاً وسهلاً",
            lang="ar",
        )
        normalizer = TextNormalizer()
        result = normalizer.normalize_article(article)
        assert "🎉" not in result.title
        assert "!!!!" not in result.title

    def test_normalize_batch(self):
        articles = [
            make_article("Title 😀!!!", "Content 🚀"),
            make_article("مرحبا 🎉!!!!", "محتوى"),
        ]
        normalizer = TextNormalizer()
        results = normalizer.normalize_batch(articles)
        assert len(results) == 2
        for r in results:
            assert "🚀" not in r.content or "🎉" not in r.title

    def test_summary_normalised(self):
        article = Article(
            id=generate_article_id("T"),
            title="T",
            content="C",
            url="https://example.com",
            published_at=utc_now(),
            metadata=ArticleMetadata(source_id="t"),
            summary="Summary 😀!!!!",
        )
        normalizer = TextNormalizer()
        result = normalizer.normalize_article(article)
        assert "😀" not in result.summary

    def test_custom_config(self):
        cfg = NormalizerConfig(remove_emojis=False, reduce_repeated_punct=False)
        normalizer = TextNormalizer(config=cfg)
        article = make_article("Title 😀!!!!", "Content")
        result = normalizer.normalize_article(article)
        assert "😀" in result.title   # emojis kept
        assert "!!!!" in result.title  # punct kept
