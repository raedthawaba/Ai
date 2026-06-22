"""Spam Detector — section 5.7.

Detects spam / low-quality promotional content using heuristic rules only.
No ML models are used.

Detection rules:
1. Keyword spam — excessive occurrence of known spam keywords
2. Repeated links — same URL appears many times
3. Repeated phrases — same 3-gram appears excessively
4. ALL-CAPS ratio — excessive shouting
5. Excessive punctuation density
6. Short content that is mostly a call-to-action
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default spam keyword lists (Arabic + English)
# ---------------------------------------------------------------------------

_DEFAULT_SPAM_KEYWORDS_EN = frozenset({
    "buy now", "click here", "free offer", "limited time", "act now",
    "exclusive deal", "best price", "discount", "sale", "subscribe",
    "make money", "earn money", "work from home", "guaranteed",
    "winner", "congratulations", "prize", "casino", "lottery",
    "click below", "sign up now", "order now", "shop now",
    "hot deal", "100% free", "no credit card", "risk free",
})

_DEFAULT_SPAM_KEYWORDS_AR = frozenset({
    "اشترِ الآن", "انقر هنا", "عرض مجاني", "وقت محدود", "خصم",
    "سعر أفضل", "فرصة ذهبية", "ربح", "فوز", "جائزة",
    "اشترك الآن", "اطلب الآن", "تسجيل مجاني", "مضمون",
    "كازينو", "مقامرة", "العمل من المنزل",
})

_SPAM_KEYWORDS = _DEFAULT_SPAM_KEYWORDS_EN | _DEFAULT_SPAM_KEYWORDS_AR

# Compiled patterns
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
_CAPS_WORD_RE = re.compile(r"\b[A-Z]{2,}\b")
_PUNCT_RE = re.compile(r"[!?؟]{2,}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SpamDetectorConfig:
    """Controls spam detection rules."""

    max_keyword_density: float = 0.05     # ratio of spam-keyword words
    max_repeated_links: int = 3           # same URL more than N times → spam
    max_phrase_repeat_ratio: float = 0.3  # 3-grams repeated too often
    max_caps_ratio: float = 0.5           # ratio of ALL-CAPS words
    max_punct_density: float = 0.1        # ratio of spam-punctuation runs
    custom_keywords: List[str] = field(default_factory=list)
    enabled_rules: List[str] = field(
        default_factory=lambda: [
            "keyword_spam",
            "repeated_links",
            "repeated_phrases",
            "caps_ratio",
            "punct_density",
        ]
    )
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Individual rule functions
# ---------------------------------------------------------------------------

def check_keyword_spam(
    text: str,
    custom_keywords: Optional[List[str]] = None,
    max_density: float = 0.05,
) -> Tuple[bool, float, str]:
    """Check whether *text* has high spam-keyword density.

    Parameters
    ----------
    text:
        Combined title + content.
    custom_keywords:
        Additional keywords to check.
    max_density:
        Maximum allowed keyword density.

    Returns
    -------
    Tuple of ``(is_spam, density, matched_keyword)``.
    """
    lower = text.lower()
    words = _WORD_RE.findall(lower)
    if not words:
        return False, 0.0, ""

    kws = _SPAM_KEYWORDS | frozenset(k.lower() for k in (custom_keywords or []))
    hits = 0
    matched = ""
    for kw in kws:
        count = lower.count(kw)
        if count:
            hits += count
            if not matched:
                matched = kw

    density = hits / len(words)
    return density > max_density, round(density, 4), matched


def check_repeated_links(text: str, max_repeats: int = 3) -> Tuple[bool, int, str]:
    """Check whether any single URL appears more than *max_repeats* times.

    Parameters
    ----------
    text:
        Content text.
    max_repeats:
        Maximum allowed occurrences of the same URL.

    Returns
    -------
    Tuple of ``(is_spam, max_count, repeated_url)``.
    """
    urls = _URL_RE.findall(text)
    if not urls:
        return False, 0, ""

    counts = Counter(u.lower() for u in urls)
    top_url, top_count = counts.most_common(1)[0]
    return top_count > max_repeats, top_count, top_url


def check_repeated_phrases(
    text: str, max_ratio: float = 0.3
) -> Tuple[bool, float]:
    """Check whether 3-grams are excessively repeated.

    Parameters
    ----------
    text:
        Content text.
    max_ratio:
        Repetition ratio above which spam is flagged.

    Returns
    -------
    Tuple of ``(is_spam, repetition_ratio)``.
    """
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if len(words) < 6:
        return False, 0.0

    trigrams = [
        f"{words[i]} {words[i+1]} {words[i+2]}"
        for i in range(len(words) - 2)
    ]
    unique = len(set(trigrams))
    ratio = 1.0 - (unique / len(trigrams))
    return ratio > max_ratio, round(ratio, 4)


def check_caps_ratio(text: str, max_ratio: float = 0.5) -> Tuple[bool, float]:
    """Check whether too many words are ALL-CAPS.

    Parameters
    ----------
    text:
        Content text.
    max_ratio:
        Maximum allowed ratio of ALL-CAPS words.

    Returns
    -------
    Tuple of ``(is_spam, ratio)``.
    """
    words = _WORD_RE.findall(text)
    if not words:
        return False, 0.0

    latin_words = [w for w in words if w.isascii() and len(w) >= 2]
    if not latin_words:
        return False, 0.0

    caps_count = sum(1 for w in latin_words if w.isupper())
    ratio = caps_count / len(latin_words)
    return ratio > max_ratio, round(ratio, 4)


def check_punct_density(text: str, max_density: float = 0.1) -> Tuple[bool, float]:
    """Check for excessive spam punctuation runs (``!!!``, ``???``).

    Parameters
    ----------
    text:
        Content text.
    max_density:
        Maximum allowed density of spam punctuation.

    Returns
    -------
    Tuple of ``(is_spam, density)``.
    """
    matches = _PUNCT_RE.findall(text)
    words = _WORD_RE.findall(text)
    if not words:
        return False, 0.0

    density = len(matches) / len(words)
    return density > max_density, round(density, 4)


# ---------------------------------------------------------------------------
# Spam detection result
# ---------------------------------------------------------------------------

@dataclass
class SpamResult:
    """Spam detection result for a single article."""

    article_id: str
    is_spam: bool
    spam_score: float
    triggered_rules: List[str] = field(default_factory=list)
    rule_details: Dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"SpamResult(id={self.article_id!r} "
            f"spam={self.is_spam} "
            f"score={self.spam_score:.3f} "
            f"rules={self.triggered_rules})"
        )


# ---------------------------------------------------------------------------
# SpamDetector
# ---------------------------------------------------------------------------

class SpamDetector:
    """Detects spam articles using heuristic rules.

    Parameters
    ----------
    config:
        :class:`SpamDetectorConfig`.
    """

    def __init__(self, config: Optional[SpamDetectorConfig] = None) -> None:
        self.config = config or SpamDetectorConfig()

    def detect(self, article: Article) -> SpamResult:
        """Run all enabled rules against *article*.

        Parameters
        ----------
        article:
            Article to inspect.

        Returns
        -------
        :class:`SpamResult`.
        """
        cfg = self.config
        text = article.title + " " + article.content
        triggered: List[str] = []
        details: Dict[str, object] = {}

        if "keyword_spam" in cfg.enabled_rules:
            is_spam, density, kw = check_keyword_spam(
                text,
                custom_keywords=cfg.custom_keywords,
                max_density=cfg.max_keyword_density,
            )
            details["keyword_density"] = density
            details["matched_keyword"] = kw
            if is_spam:
                triggered.append("keyword_spam")

        if "repeated_links" in cfg.enabled_rules:
            is_spam, count, url = check_repeated_links(text, cfg.max_repeated_links)
            details["max_link_repeats"] = count
            details["repeated_url"] = url
            if is_spam:
                triggered.append("repeated_links")

        if "repeated_phrases" in cfg.enabled_rules:
            is_spam, ratio = check_repeated_phrases(text, cfg.max_phrase_repeat_ratio)
            details["phrase_repeat_ratio"] = ratio
            if is_spam:
                triggered.append("repeated_phrases")

        if "caps_ratio" in cfg.enabled_rules:
            is_spam, ratio = check_caps_ratio(text, cfg.max_caps_ratio)
            details["caps_ratio"] = ratio
            if is_spam:
                triggered.append("caps_ratio")

        if "punct_density" in cfg.enabled_rules:
            is_spam, density = check_punct_density(text, cfg.max_punct_density)
            details["punct_density"] = density
            if is_spam:
                triggered.append("punct_density")

        spam_score = len(triggered) / max(len(cfg.enabled_rules), 1)
        is_spam_final = bool(triggered)

        return SpamResult(
            article_id=article.id,
            is_spam=is_spam_final,
            spam_score=round(spam_score, 4),
            triggered_rules=triggered,
            rule_details=details,
        )

    def filter_batch(
        self, articles: List[Article]
    ) -> Tuple[List[Article], List[SpamResult]]:
        """Detect and remove spam from *articles*.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        Tuple of ``(clean_articles, all_results)``.
        """
        clean: List[Article] = []
        all_results: List[SpamResult] = []

        for article in articles:
            result = self.detect(article)
            all_results.append(result)
            if not result.is_spam:
                clean.append(article)
            else:
                logger.debug(
                    "SpamDetector: spam id=%s rules=%s score=%.2f",
                    article.id,
                    result.triggered_rules,
                    result.spam_score,
                )

        logger.info(
            "SpamDetector.filter_batch: in=%d clean=%d spam=%d",
            len(articles),
            len(clean),
            len(articles) - len(clean),
        )
        return clean, all_results
