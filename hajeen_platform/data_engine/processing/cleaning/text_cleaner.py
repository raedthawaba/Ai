"""Text Cleaner — section 4.10.

Cleans and normalises article text with full Arabic language support.
All functions are pure (no side-effects) and operate on strings.

Capabilities:
- HTML tag / entity stripping
- Arabic-specific normalisation (harakat, alef variants, tatweel)
- Whitespace / punctuation normalisation
- URL / email / mention removal
- Article-level cleaner that returns a cleaned copy
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_RE_HTML_TAG = re.compile(r"<[^>]+>", re.UNICODE)
_RE_HTML_ENTITY = re.compile(r"&[a-zA-Z]{2,8};|&#\d{1,5};", re.UNICODE)
_RE_URL = re.compile(
    r"https?://\S+|www\.\S+",
    re.IGNORECASE | re.UNICODE,
)
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", re.UNICODE)
_RE_MENTION = re.compile(r"@\w+", re.UNICODE)
_RE_HASHTAG = re.compile(r"#\w+", re.UNICODE)
_RE_MULTI_SPACE = re.compile(r"[ \t]+", re.UNICODE)
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}", re.UNICODE)
_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", re.UNICODE)

# Arabic-specific patterns
_RE_HARAKAT = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]",
    re.UNICODE,
)
_RE_TATWEEL = re.compile(r"\u0640+", re.UNICODE)

# Alef variants → plain alef (ا)
_ALEF_VARIANTS = str.maketrans(
    "أإآٱٲٳ",
    "اااااا",
)
# Teh marbuta → heh, waw variants → waw
_TA_MARBUTA = str.maketrans("ةۃ", "هه")
_WAW_VARIANTS = str.maketrans("ؤ", "و")
_YEH_VARIANTS = str.maketrans("ىئ", "يي")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CleanerConfig:
    """Runtime configuration for :class:`TextCleaner`."""

    strip_html: bool = True
    decode_html_entities: bool = True
    remove_urls: bool = True
    remove_emails: bool = True
    remove_mentions: bool = False
    remove_hashtags: bool = False
    normalize_arabic: bool = True
    remove_harakat: bool = True
    remove_tatweel: bool = True
    normalize_alef: bool = True
    normalize_ta_marbuta: bool = False
    normalize_unicode: bool = True
    fix_whitespace: bool = True
    min_length: int = 0
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Low-level cleaning functions
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Remove all HTML tags from *text*."""
    return _RE_HTML_TAG.sub(" ", text)


def decode_html_entities(text: str) -> str:
    """Replace HTML entities (``&amp;``, ``&#160;`` …) with their characters."""
    text = html.unescape(text)
    text = _RE_HTML_ENTITY.sub(" ", text)
    return text


def remove_urls(text: str) -> str:
    """Remove HTTP / HTTPS URLs and bare ``www.`` links."""
    return _RE_URL.sub(" ", text)


def remove_emails(text: str) -> str:
    """Remove e-mail addresses."""
    return _RE_EMAIL.sub(" ", text)


def remove_mentions(text: str) -> str:
    """Remove ``@mention`` tokens."""
    return _RE_MENTION.sub(" ", text)


def remove_hashtags(text: str) -> str:
    """Remove ``#hashtag`` tokens."""
    return _RE_HASHTAG.sub(" ", text)


def remove_harakat(text: str) -> str:
    """Remove Arabic diacritics (tashkeel / harakat)."""
    return _RE_HARAKAT.sub("", text)


def remove_tatweel(text: str) -> str:
    """Remove Arabic tatweel / kashida (elongation character U+0640)."""
    return _RE_TATWEEL.sub("", text)


def normalize_alef(text: str) -> str:
    """Normalise alef variants (أ إ آ ٱ) to plain alef (ا)."""
    return text.translate(_ALEF_VARIANTS)


def normalize_ta_marbuta(text: str) -> str:
    """Replace teh marbuta (ة) with heh (ه) for root-level matching."""
    return text.translate(_TA_MARBUTA)


def normalize_waw(text: str) -> str:
    """Replace hamzated waw (ؤ) with plain waw (و)."""
    return text.translate(_WAW_VARIANTS)


def normalize_yeh(text: str) -> str:
    """Replace yeh variants (ى ئ) with yeh (ي)."""
    return text.translate(_YEH_VARIANTS)


def normalize_unicode(text: str) -> str:
    """Apply NFC unicode normalisation to collapse combining characters."""
    return unicodedata.normalize("NFC", text)


def fix_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs to a single space; collapse 3+ newlines to 2."""
    text = _RE_CONTROL.sub("", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def clean_text(text: str, config: Optional[CleanerConfig] = None) -> str:
    """Apply the full cleaning pipeline to a single text string.

    Parameters
    ----------
    text:
        Input string to clean.
    config:
        :class:`CleanerConfig` instance controlling which steps run.
        Defaults to the standard configuration.

    Returns
    -------
    Cleaned string.
    """
    if not text:
        return ""

    cfg = config or CleanerConfig()

    if cfg.decode_html_entities:
        text = decode_html_entities(text)
    if cfg.strip_html:
        text = strip_html(text)
    if cfg.remove_urls:
        text = remove_urls(text)
    if cfg.remove_emails:
        text = remove_emails(text)
    if cfg.remove_mentions:
        text = remove_mentions(text)
    if cfg.remove_hashtags:
        text = remove_hashtags(text)
    if cfg.normalize_unicode:
        text = normalize_unicode(text)
    if cfg.normalize_arabic:
        if cfg.remove_harakat:
            text = remove_harakat(text)
        if cfg.remove_tatweel:
            text = remove_tatweel(text)
        if cfg.normalize_alef:
            text = normalize_alef(text)
        if cfg.normalize_ta_marbuta:
            text = normalize_ta_marbuta(text)
    if cfg.fix_whitespace:
        text = fix_whitespace(text)

    return text


# ---------------------------------------------------------------------------
# Article-level cleaner
# ---------------------------------------------------------------------------

class TextCleaner:
    """Article-level cleaner that returns immutable cleaned copies.

    Parameters
    ----------
    config:
        :class:`CleanerConfig` applied to every article.
    """

    def __init__(self, config: Optional[CleanerConfig] = None) -> None:
        self.config = config or CleanerConfig()

    def clean_article(self, article: Article) -> Article:
        """Return a new :class:`Article` with cleaned title and content.

        The original article is not modified.

        Parameters
        ----------
        article:
            Source article to clean.

        Returns
        -------
        A new Article instance with cleaned fields.
        """
        new_title = clean_text(article.title, self.config)
        new_content = clean_text(article.content, self.config)
        new_summary = (
            clean_text(article.summary, self.config)
            if article.summary
            else None
        )

        if not new_title:
            new_title = article.title
        if not new_content:
            new_content = article.content

        cleaned = article.model_copy(
            update={
                "title": new_title,
                "content": new_content,
                "summary": new_summary,
            }
        )
        logger.debug(
            "TextCleaner: id=%s title_len=%d->%d content_len=%d->%d",
            article.id,
            len(article.title),
            len(new_title),
            len(article.content),
            len(new_content),
        )
        return cleaned

    def clean_batch(self, articles: list[Article]) -> list[Article]:
        """Clean a list of articles.

        Parameters
        ----------
        articles:
            List of articles to clean.

        Returns
        -------
        List of cleaned Article copies.
        """
        result = [self.clean_article(a) for a in articles]
        logger.info("TextCleaner.clean_batch: processed=%d", len(result))
        return result
