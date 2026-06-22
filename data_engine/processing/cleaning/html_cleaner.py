"""HTML Cleaner — section 5.2.

Converts raw HTML into clean plain text, with full Arabic support.

Dependencies: beautifulsoup4, trafilatura (optional — falls back to bs4).

Capabilities:
- remove_scripts()     — strip <script>, <style>, <noscript>
- remove_ads()         — strip known ad / tracking selectors
- extract_main_content() — trafilatura-first extraction with bs4 fallback
- remove_html()        — full tag stripping via bs4
- normalize_whitespace() — collapse runs of spaces and newlines
- HTMLCleaner          — article-level class
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Comment

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# Trafilatura is optional — imported lazily to avoid hard failures
try:
    import trafilatura  # type: ignore[import]
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False
    logger.info("html_cleaner: trafilatura not available; using bs4-only extraction")

# ---------------------------------------------------------------------------
# Ad / noise CSS selectors
# ---------------------------------------------------------------------------

_AD_SELECTORS = [
    "[class*='ad']", "[class*='ads']", "[class*='advertisement']",
    "[class*='sponsor']", "[class*='promo']", "[class*='banner']",
    "[class*='popup']", "[class*='modal']", "[id*='ad']", "[id*='ads']",
    "[id*='advertisement']", "[id*='banner']", "[id*='popup']",
    "aside", "nav", "footer", "header",
    "[role='complementary']", "[role='navigation']",
    ".sidebar", ".widget", ".related-posts", ".comments",
]

_NOISE_TAGS = {
    "script", "style", "noscript", "iframe", "embed", "object",
    "form", "button", "select", "input", "textarea",
    "svg", "canvas",
}

_RE_MULTI_SPACE = re.compile(r"[ \t]+")
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}")
_RE_BLANK_LINE = re.compile(r"^\s+$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _make_soup(html: str, parser: str = "lxml") -> BeautifulSoup:
    """Create a BeautifulSoup instance, falling back to html.parser."""
    try:
        return BeautifulSoup(html, parser)
    except Exception:
        return BeautifulSoup(html, "html.parser")


def remove_scripts(html: str) -> str:
    """Strip all ``<script>``, ``<style>``, and ``<noscript>`` tags from *html*.

    Parameters
    ----------
    html:
        Raw HTML string.

    Returns
    -------
    HTML string with noise tags removed.
    """
    soup = _make_soup(html)
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    return str(soup)


def remove_ads(html: str) -> str:
    """Remove common ad/navigation/sidebar elements from *html*.

    Parameters
    ----------
    html:
        Raw HTML string.

    Returns
    -------
    HTML string with ad elements removed.
    """
    soup = _make_soup(html)
    for selector in _AD_SELECTORS:
        try:
            for el in soup.select(selector):
                el.decompose()
        except Exception:
            pass
    return str(soup)


def remove_html(html: str) -> str:
    """Strip ALL HTML tags and return clean plain text.

    Parameters
    ----------
    html:
        Raw HTML string.

    Returns
    -------
    Plain text with no HTML tags.
    """
    soup = _make_soup(html)
    return soup.get_text(separator=" ", strip=True)


def extract_main_content(html: str, language: str = "en") -> str:
    """Extract the main readable content from *html*.

    Uses trafilatura when available for best accuracy; falls back to
    a BeautifulSoup heuristic (``<article>``, ``<main>``, ``<body>``).

    Parameters
    ----------
    html:
        Raw HTML string.
    language:
        ISO language hint passed to trafilatura (``"ar"``, ``"en"`` …).

    Returns
    -------
    Extracted plain text.
    """
    if not html or not html.strip():
        return ""

    if _TRAFILATURA_AVAILABLE:
        try:
            result = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                target_language=language if language != "ar" else None,
            )
            if result and len(result.strip()) > 50:
                return normalize_whitespace(result)
        except Exception as exc:
            logger.debug("trafilatura extraction failed: %s", exc)

    # bs4 fallback
    soup = _make_soup(html)
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()

    for selector in ["article", "main", '[role="main"]', ".content",
                     ".article-body", ".post-content", ".entry-content"]:
        try:
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    return normalize_whitespace(text)
        except Exception:
            pass

    body = soup.find("body")
    if body:
        return normalize_whitespace(body.get_text(separator=" ", strip=True))

    return normalize_whitespace(soup.get_text(separator=" ", strip=True))


def normalize_whitespace(text: str) -> str:
    """Collapse redundant whitespace in plain text.

    Parameters
    ----------
    text:
        Input plain text.

    Returns
    -------
    Cleaned text with normalised spacing.
    """
    if not text:
        return ""
    text = _RE_BLANK_LINE.sub("", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def clean_html(html: str, language: str = "en") -> str:
    """Full pipeline: scripts → ads → extract main content → normalise.

    Parameters
    ----------
    html:
        Raw HTML string.
    language:
        ISO language hint.

    Returns
    -------
    Clean plain text.
    """
    if not html or not html.strip():
        return ""
    html = remove_scripts(html)
    html = remove_ads(html)
    return extract_main_content(html, language=language)


# ---------------------------------------------------------------------------
# Article-level cleaner
# ---------------------------------------------------------------------------

class HTMLCleaner:
    """Cleans HTML-bearing article fields using the full pipeline.

    Parameters
    ----------
    use_trafilatura:
        When ``True`` (default) try trafilatura before the bs4 fallback.
    """

    def __init__(self, use_trafilatura: bool = True) -> None:
        self._use_trafilatura = use_trafilatura and _TRAFILATURA_AVAILABLE

    def clean_article(self, article: Article) -> Article:
        """Return a cleaned copy of *article*.

        Cleans ``title`` and ``content`` fields.  The original is not mutated.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        New Article with clean text fields.
        """
        lang = article.metadata.language or "en"

        new_title = _strip_light(article.title)
        new_content = clean_html(article.content, language=lang) if _looks_like_html(article.content) else normalize_whitespace(article.content)
        new_summary = (
            _strip_light(article.summary)
            if article.summary
            else None
        )

        if not new_title:
            new_title = article.title
        if not new_content:
            new_content = article.content

        return article.model_copy(
            update={"title": new_title, "content": new_content, "summary": new_summary}
        )

    def clean_batch(self, articles: list[Article]) -> list[Article]:
        """Clean a list of articles.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of cleaned Article copies.
        """
        result = [self.clean_article(a) for a in articles]
        logger.info("HTMLCleaner.clean_batch: processed=%d", len(result))
        return result


def _looks_like_html(text: str) -> bool:
    """Return True when *text* contains HTML tags."""
    return bool(re.search(r"<[a-zA-Z/][^>]*>", text))


def _strip_light(text: str) -> str:
    """Remove tags from a short string (title, summary) without full extraction."""
    soup = _make_soup(text)
    return soup.get_text(separator=" ", strip=True)
