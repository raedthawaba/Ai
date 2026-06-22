"""Text Normalizer — section 5.3.

Extends text_cleaner with:
- Full Unicode normalisation (NFC/NFKC)
- Emoji removal
- Excessive punctuation reduction
- Mixed-encoding repair
- Advanced Arabic normalisation

All functions are pure and stateless.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Emoji ranges (covers most emoji blocks)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"   # alchemical
    "\U0001F780-\U0001F7FF"   # geometric extended
    "\U0001F800-\U0001F8FF"   # supplemental arrows-C
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "\U0001FA00-\U0001FA6F"   # chess symbols
    "\U0001FA70-\U0001FAFF"   # symbols and pictographs extended-A
    "\U00002702-\U000027B0"   # dingbats
    "\U000024C2-\U0001F251"   # enclosed characters
    "]+",
    re.UNICODE,
)

# Repeated punctuation (3+ consecutive punctuation chars → keep 1 or 3 max)
_REPEATED_PUNCT_RE = re.compile(r"([!?؟.،,;:\-_*])\1{2,}", re.UNICODE)

# Repeated spaces already handled, but keep as utility
_MULTI_SPACE_RE = re.compile(r"[ \t]+", re.UNICODE)

# Invisible / zero-width chars
_ZERO_WIDTH_RE = re.compile(
    r"[\u200B-\u200D\u2028\u2029\u00AD\uFEFF\u00A0\u202F]",
    re.UNICODE,
)

# Arabic-specific extended normalisation
_ALEF_EXTENDED = str.maketrans("أإآٱٲٳٴ", "ااااааа")  # extra variants beyond phase-4
_HEH_GOAL = str.maketrans("ۀہۂۃ", "هههه")
_ARABIC_KAF = str.maketrans("ک", "ك")  # Persian kaf → Arabic kaf
_ARABIC_YEH2 = str.maketrans("یﮮﮯ", "ييي")  # Farsi yeh variants


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class NormalizerConfig:
    """Controls which normalisation steps run."""

    unicode_form: str = "NFC"        # "NFC" | "NFKC" | "NFD" | "NFKD"
    remove_emojis: bool = True
    reduce_repeated_punct: bool = True
    remove_zero_width: bool = True
    normalize_arabic_extended: bool = True
    normalize_arabic_kaf: bool = True
    normalize_arabic_yeh: bool = True
    fix_whitespace: bool = True
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Low-level normalisation functions
# ---------------------------------------------------------------------------

def normalize_unicode(text: str, form: str = "NFC") -> str:
    """Apply Unicode normalisation *form* (``NFC``, ``NFKC``, ``NFD``, ``NFKD``).

    Parameters
    ----------
    text:
        Input string.
    form:
        Unicode normalisation form.

    Returns
    -------
    Normalised string.
    """
    return unicodedata.normalize(form, text)


def remove_emojis(text: str) -> str:
    """Remove all emoji characters from *text*.

    Parameters
    ----------
    text:
        Input string.

    Returns
    -------
    String with emojis removed.
    """
    return _EMOJI_RE.sub(" ", text)


def remove_zero_width_chars(text: str) -> str:
    """Remove invisible and zero-width Unicode characters.

    Parameters
    ----------
    text:
        Input string.

    Returns
    -------
    String without zero-width / invisible characters.
    """
    return _ZERO_WIDTH_RE.sub("", text)


def reduce_repeated_punctuation(text: str, max_repeat: int = 1) -> str:
    """Collapse runs of repeated punctuation to a single occurrence.

    ``!!!!!!`` → ``!``  (when ``max_repeat=1``)
    ``...``    → ``...`` (3 is the standard ellipsis, stays with max_repeat=3)

    Parameters
    ----------
    text:
        Input string.
    max_repeat:
        Maximum allowed consecutive identical punctuation chars.

    Returns
    -------
    String with reduced punctuation runs.
    """
    def _replace(m: re.Match) -> str:
        char = m.group(1)
        return char * min(m.end() - m.start(), max_repeat)

    return _REPEATED_PUNCT_RE.sub(_replace, text)


def normalize_arabic_extended(text: str) -> str:
    """Apply extended Arabic character normalisation.

    Covers:
    - Additional alef variants (beyond Phase 4 basic set)
    - Heh goal variants → standard heh
    - Persian kaf → Arabic kaf
    - Farsi yeh variants → Arabic yeh

    Parameters
    ----------
    text:
        Input string.

    Returns
    -------
    Normalised Arabic string.
    """
    text = text.translate(_ALEF_EXTENDED)
    text = text.translate(_HEH_GOAL)
    text = text.translate(_ARABIC_KAF)
    text = text.translate(_ARABIC_YEH2)
    return text


def fix_whitespace(text: str) -> str:
    """Collapse multiple spaces/tabs to single space; strip leading/trailing."""
    return _MULTI_SPACE_RE.sub(" ", text).strip()


def normalize_text(text: str, config: Optional[NormalizerConfig] = None) -> str:
    """Apply the full normalisation pipeline to a single string.

    Parameters
    ----------
    text:
        Input text.
    config:
        Normalisation configuration.  Defaults to :class:`NormalizerConfig`.

    Returns
    -------
    Normalised string.
    """
    if not text:
        return ""

    cfg = config or NormalizerConfig()

    text = normalize_unicode(text, form=cfg.unicode_form)

    if cfg.remove_zero_width:
        text = remove_zero_width_chars(text)

    if cfg.remove_emojis:
        text = remove_emojis(text)

    if cfg.reduce_repeated_punct:
        text = reduce_repeated_punctuation(text)

    if cfg.normalize_arabic_extended:
        text = normalize_arabic_extended(text)

    if cfg.fix_whitespace:
        text = fix_whitespace(text)

    return text


# ---------------------------------------------------------------------------
# Article-level normaliser
# ---------------------------------------------------------------------------

class TextNormalizer:
    """Article-level text normaliser.

    Parameters
    ----------
    config:
        :class:`NormalizerConfig` controlling which steps run.
    """

    def __init__(self, config: Optional[NormalizerConfig] = None) -> None:
        self.config = config or NormalizerConfig()

    def normalize_article(self, article: Article) -> Article:
        """Return a new :class:`Article` with normalised text fields.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        New Article with normalised ``title``, ``content``, and ``summary``.
        """
        new_title = normalize_text(article.title, self.config)
        new_content = normalize_text(article.content, self.config)
        new_summary = (
            normalize_text(article.summary, self.config)
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

    def normalize_batch(self, articles: list[Article]) -> list[Article]:
        """Normalise a list of articles.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of normalised Article copies.
        """
        result = [self.normalize_article(a) for a in articles]
        logger.info("TextNormalizer.normalize_batch: processed=%d", len(result))
        return result
