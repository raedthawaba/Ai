"""Language Filter — section 5.5.

Detects the language of article content and filters by allowed languages.

Primary detector: langdetect (probabilistic, supports Arabic/English/50+ langs).
Fallback: character-set heuristic from Phase 4's content_filter module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try langdetect — fall back gracefully if unavailable
# ---------------------------------------------------------------------------

try:
    from langdetect import detect, detect_langs, LangDetectException  # type: ignore[import]
    from langdetect import DetectorFactory  # type: ignore[import]
    DetectorFactory.seed = 42          # make results deterministic
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False
    LangDetectException = Exception    # type: ignore[misc, assignment]
    logger.info("language_filter: langdetect unavailable; using heuristic fallback")

# Heuristic helpers (same approach as Phase-4 content_filter)
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_LATIN_RE = re.compile(r"[a-zA-Z]")
_MIN_TEXT_FOR_LANGDETECT = 20


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LanguageFilterConfig:
    """Controls language detection and filtering."""

    allowed_languages: List[str] = field(default_factory=lambda: ["ar", "en"])
    min_confidence: float = 0.7
    fallback_to_metadata: bool = True
    tag_detected_language: bool = True
    min_text_length: int = 20
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

@dataclass
class LanguageDetectionResult:
    """Result of a language detection attempt."""

    language: str
    confidence: float
    method: str              # "langdetect" | "heuristic" | "metadata" | "unknown"
    all_scores: Dict[str, float] = field(default_factory=dict)


def detect_language(
    text: str,
    min_confidence: float = 0.7,
) -> LanguageDetectionResult:
    """Detect the dominant language of *text*.

    Uses langdetect when available; falls back to a character-set heuristic.

    Parameters
    ----------
    text:
        Text to analyse (title + content recommended).
    min_confidence:
        Minimum confidence for langdetect result.  Falls back to heuristic
        when below threshold.

    Returns
    -------
    :class:`LanguageDetectionResult`.
    """
    if not text or len(text.strip()) < _MIN_TEXT_FOR_LANGDETECT:
        return LanguageDetectionResult(
            language="unknown", confidence=0.0, method="unknown"
        )

    # Try langdetect first
    if _LANGDETECT_AVAILABLE:
        try:
            probs = detect_langs(text)
            scores: Dict[str, float] = {
                str(p.lang): round(p.prob, 4) for p in probs
            }
            top = probs[0]
            if top.prob >= min_confidence:
                return LanguageDetectionResult(
                    language=str(top.lang),
                    confidence=top.prob,
                    method="langdetect",
                    all_scores=scores,
                )
            # Low confidence — still return best guess but note it
            return LanguageDetectionResult(
                language=str(top.lang),
                confidence=top.prob,
                method="langdetect_low_confidence",
                all_scores=scores,
            )
        except LangDetectException:
            pass
        except Exception as exc:
            logger.debug("langdetect error: %s", exc)

    # Heuristic fallback
    arabic_chars = len(_ARABIC_RE.findall(text))
    latin_chars = len(_LATIN_RE.findall(text))
    total = arabic_chars + latin_chars

    if total == 0:
        return LanguageDetectionResult(
            language="unknown", confidence=0.0, method="heuristic"
        )

    arabic_ratio = arabic_chars / total
    if arabic_ratio >= 0.5:
        return LanguageDetectionResult(
            language="ar",
            confidence=round(arabic_ratio, 4),
            method="heuristic",
        )
    return LanguageDetectionResult(
        language="en",
        confidence=round(1 - arabic_ratio, 4),
        method="heuristic",
    )


# ---------------------------------------------------------------------------
# Language filter result
# ---------------------------------------------------------------------------

@dataclass
class LanguageFilterResult:
    """Result of a language filtering pass."""

    kept: List[Article] = field(default_factory=list)
    rejected: List[Article] = field(default_factory=list)
    detection_map: Dict[str, LanguageDetectionResult] = field(default_factory=dict)

    @property
    def keep_rate(self) -> float:
        total = len(self.kept) + len(self.rejected)
        return len(self.kept) / total if total else 1.0


# ---------------------------------------------------------------------------
# LanguageFilter
# ---------------------------------------------------------------------------

class LanguageFilter:
    """Detects article language and filters by allowed language list.

    Parameters
    ----------
    config:
        :class:`LanguageFilterConfig`.
    """

    def __init__(self, config: Optional[LanguageFilterConfig] = None) -> None:
        self.config = config or LanguageFilterConfig()

    def filter_batch(
        self, articles: List[Article]
    ) -> LanguageFilterResult:
        """Filter *articles* to keep only allowed languages.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        :class:`LanguageFilterResult`.
        """
        cfg = self.config
        result = LanguageFilterResult()

        for article in articles:
            detection = self._detect(article)
            result.detection_map[article.id] = detection
            lang = detection.language

            # Tag the article's metadata with detected language
            # Only update if lang is a valid 2-letter ISO code
            tagged = article
            if cfg.tag_detected_language and len(lang) == 2 and lang.isalpha():
                try:
                    new_meta = article.metadata.model_copy(
                        update={"language": lang}
                    )
                    tagged = article.model_copy(update={"metadata": new_meta})
                except Exception:
                    pass

            if not cfg.allowed_languages or lang in cfg.allowed_languages:
                result.kept.append(tagged)
            else:
                result.rejected.append(tagged)
                logger.debug(
                    "LanguageFilter: rejected id=%s lang=%s", article.id, lang
                )

        logger.info(
            "LanguageFilter.filter_batch: in=%d kept=%d rejected=%d",
            len(articles),
            len(result.kept),
            len(result.rejected),
        )
        return result

    def detect(self, article: Article) -> LanguageDetectionResult:
        """Detect language for a single article (public wrapper).

        Parameters
        ----------
        article:
            Article to inspect.

        Returns
        -------
        :class:`LanguageDetectionResult`.
        """
        return self._detect(article)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect(self, article: Article) -> LanguageDetectionResult:
        """Detect language for a single article."""
        cfg = self.config

        text = (article.title + " " + article.content).strip()
        if len(text) < cfg.min_text_length:
            if cfg.fallback_to_metadata and article.metadata.language:
                return LanguageDetectionResult(
                    language=article.metadata.language,
                    confidence=1.0,
                    method="metadata",
                )
            return LanguageDetectionResult(
                language="unknown", confidence=0.0, method="unknown"
            )

        det = detect_language(text, min_confidence=cfg.min_confidence)

        # If uncertain, try metadata fallback
        if det.language == "unknown" and cfg.fallback_to_metadata:
            if article.metadata.language:
                return LanguageDetectionResult(
                    language=article.metadata.language,
                    confidence=1.0,
                    method="metadata",
                )

        return det
