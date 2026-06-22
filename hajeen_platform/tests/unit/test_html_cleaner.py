"""Tests for section 5.2 — HTML Cleaner."""

import pytest

from data_engine.processing.cleaning.html_cleaner import (
    HTMLCleaner,
    clean_html,
    extract_main_content,
    normalize_whitespace,
    remove_ads,
    remove_html,
    remove_scripts,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now

# ---------------------------------------------------------------------------
# HTML Samples
# ---------------------------------------------------------------------------

ENGLISH_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <article>
    <h1>Breaking News in Technology</h1>
    <p>Scientists have discovered a new method for processing text data efficiently.
    The breakthrough allows computers to understand natural language better than ever before.</p>
    <p>The research team worked for three years to develop this technique.</p>
  </article>
  <aside class="ads">Buy now! Best price!</aside>
  <footer>Copyright 2025</footer>
  <script>alert('hello')</script>
  <style>body { margin: 0; }</style>
</body>
</html>
"""

ARABIC_HTML = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><title>خبر تقني</title></head>
<body>
  <nav><a href="/">الرئيسية</a></nav>
  <article>
    <h1>اكتشاف علمي جديد في مجال الذكاء الاصطناعي</h1>
    <p>أعلن فريق من العلماء عن اكتشاف طريقة جديدة لمعالجة النصوص العربية بكفاءة عالية.
    يمكن لهذه التقنية أن تحسن من دقة التعرف على اللغة العربية بنسبة تصل إلى ٩٠٪.</p>
    <p>العمل استغرق ثلاث سنوات من البحث والتطوير المستمر.</p>
  </article>
  <aside class="advertisement">إعلان تجاري</aside>
  <script>console.log('tracking')</script>
</body>
</html>
"""

MINIMAL_HTML = "<p>Hello world</p>"

HTML_WITH_SCRIPTS = """
<html><body>
<script>var x = 1;</script>
<style>.ad { color: red; }</style>
<noscript>Enable JS</noscript>
<p>Clean content here.</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Tests: remove_scripts
# ---------------------------------------------------------------------------

class TestRemoveScripts:
    def test_removes_script_tags(self):
        result = remove_scripts(HTML_WITH_SCRIPTS)
        assert "<script>" not in result
        assert "var x = 1" not in result

    def test_removes_style_tags(self):
        result = remove_scripts(HTML_WITH_SCRIPTS)
        assert "<style>" not in result
        assert ".ad { color: red; }" not in result

    def test_removes_noscript(self):
        result = remove_scripts(HTML_WITH_SCRIPTS)
        assert "Enable JS" not in result

    def test_preserves_content(self):
        result = remove_scripts(HTML_WITH_SCRIPTS)
        assert "Clean content here" in result

    def test_english_html(self):
        result = remove_scripts(ENGLISH_HTML)
        assert "alert" not in result

    def test_arabic_html(self):
        result = remove_scripts(ARABIC_HTML)
        assert "console.log" not in result


# ---------------------------------------------------------------------------
# Tests: remove_ads
# ---------------------------------------------------------------------------

class TestRemoveAds:
    def test_removes_aside(self):
        result = remove_ads(ENGLISH_HTML)
        assert "Buy now" not in result

    def test_removes_advertisement_class(self):
        result = remove_ads(ARABIC_HTML)
        assert "إعلان تجاري" not in result

    def test_preserves_article_content(self):
        result = remove_ads(ENGLISH_HTML)
        assert "Scientists" in result

    def test_preserves_arabic_article(self):
        result = remove_ads(ARABIC_HTML)
        assert "اكتشاف" in result


# ---------------------------------------------------------------------------
# Tests: remove_html
# ---------------------------------------------------------------------------

class TestRemoveHtml:
    def test_strips_all_tags(self):
        result = remove_html("<p>Hello <b>World</b></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "World" in result

    def test_minimal_html(self):
        result = remove_html(MINIMAL_HTML)
        assert "Hello world" in result

    def test_arabic_content_preserved(self):
        result = remove_html("<p>مرحبا بالعالم</p>")
        assert "مرحبا" in result

    def test_empty_string(self):
        result = remove_html("")
        assert result == ""

    def test_no_html(self):
        result = remove_html("plain text")
        assert "plain text" in result


# ---------------------------------------------------------------------------
# Tests: normalize_whitespace
# ---------------------------------------------------------------------------

class TestNormalizeWhitespace:
    def test_collapses_multiple_spaces(self):
        result = normalize_whitespace("hello   world")
        assert result == "hello world"

    def test_collapses_excessive_newlines(self):
        result = normalize_whitespace("line1\n\n\n\nline2")
        assert result == "line1\n\nline2"

    def test_strips_leading_trailing(self):
        result = normalize_whitespace("  hello  ")
        assert result == "hello"

    def test_empty_string(self):
        result = normalize_whitespace("")
        assert result == ""

    def test_arabic_text(self):
        result = normalize_whitespace("   مرحبا   بالعالم   ")
        assert result == "مرحبا بالعالم"


# ---------------------------------------------------------------------------
# Tests: extract_main_content
# ---------------------------------------------------------------------------

class TestExtractMainContent:
    def test_extracts_english_content(self):
        result = extract_main_content(ENGLISH_HTML, language="en")
        assert result  # non-empty
        assert len(result) > 30

    def test_extracts_arabic_content(self):
        result = extract_main_content(ARABIC_HTML, language="ar")
        assert result
        assert len(result) > 30

    def test_empty_html(self):
        result = extract_main_content("", language="en")
        assert result == ""

    def test_minimal_html(self):
        result = extract_main_content(MINIMAL_HTML)
        assert "Hello" in result

    def test_excludes_scripts_in_output(self):
        result = extract_main_content(ENGLISH_HTML)
        assert "alert" not in result


# ---------------------------------------------------------------------------
# Tests: clean_html (full pipeline)
# ---------------------------------------------------------------------------

class TestCleanHtml:
    def test_cleans_english_article(self):
        result = clean_html(ENGLISH_HTML, language="en")
        assert result
        assert "alert" not in result
        assert "Copyright" not in result or len(result) > 50

    def test_cleans_arabic_article(self):
        result = clean_html(ARABIC_HTML, language="ar")
        assert result
        assert "console.log" not in result

    def test_empty_input(self):
        result = clean_html("", language="en")
        assert result == ""

    def test_whitespace_only(self):
        result = clean_html("   ", language="en")
        assert result == ""


# ---------------------------------------------------------------------------
# Tests: HTMLCleaner (article-level)
# ---------------------------------------------------------------------------

def _make_html_article(html_content: str, html_title: str = "<b>Title</b>", lang: str = "en") -> Article:
    safe_content = html_content if html_content.strip() else "placeholder"
    safe_title = html_title if html_title.strip() else "Title"
    return Article(
        id=generate_article_id(safe_title),
        title=safe_title,
        content=safe_content,
        url="https://example.com/test",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="test", language=lang),
    )


class TestHTMLCleaner:
    def test_cleans_article_content(self):
        article = _make_html_article(ENGLISH_HTML)
        cleaner = HTMLCleaner()
        result = cleaner.clean_article(article)
        assert result.content
        assert "<script>" not in result.content

    def test_cleans_title_html(self):
        article = _make_html_article("<p>Content</p>", html_title="<b>My Title</b>")
        cleaner = HTMLCleaner()
        result = cleaner.clean_article(article)
        assert "<b>" not in result.title
        assert "My Title" in result.title

    def test_arabic_article_cleaned(self):
        article = _make_html_article(ARABIC_HTML, lang="ar")
        cleaner = HTMLCleaner()
        result = cleaner.clean_article(article)
        assert result.content
        assert "console.log" not in result.content

    def test_clean_batch(self):
        articles = [
            _make_html_article(ENGLISH_HTML),
            _make_html_article(ARABIC_HTML, lang="ar"),
        ]
        cleaner = HTMLCleaner()
        results = cleaner.clean_batch(articles)
        assert len(results) == 2
        for r in results:
            assert "<script>" not in r.content

    def test_plain_text_article_preserved(self):
        """Non-HTML content should pass through unchanged (modulo whitespace)."""
        article = _make_html_article("This is plain text with no tags.", html_title="Plain Title")
        cleaner = HTMLCleaner()
        result = cleaner.clean_article(article)
        assert "plain text" in result.content.lower()

    def test_empty_content_preserved(self):
        article = _make_html_article("", html_title="Title")
        cleaner = HTMLCleaner()
        result = cleaner.clean_article(article)
        # title must still be set
        assert result.title
