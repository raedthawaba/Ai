"""Sentiment Analyzer — Phase 2 (Section 2.4).

تحليل المشاعر بدون نماذج ML ثقيلة.

الطريقة:
- VADER-style lexicon scoring (إذا توفّر vaderSentiment)
- قاموس عربي وإنجليزي مدمج fallback
- مزج Titel + Content مع ترجيح العنوان
- نتيجة ثلاثية: positive / negative / neutral
- درجة compound في [-1.0, +1.0]
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Optional VADER import
# ─────────────────────────────────────────────────────────────────────────────

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore[import]
    _VADER_AVAILABLE = True
    logger.info("sentiment_analyzer: vaderSentiment متاح")
except ImportError:
    _VADER_AVAILABLE = False
    logger.info("sentiment_analyzer: vaderSentiment غير متاح — استخدام قاموس fallback")

# ─────────────────────────────────────────────────────────────────────────────
# Fallback sentiment lexicons
# ─────────────────────────────────────────────────────────────────────────────

_POSITIVE_EN = frozenset([
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "positive", "success", "successful", "happy", "joy", "love", "best",
    "perfect", "outstanding", "exceptional", "impressive", "brilliant",
    "effective", "innovative", "improvement", "growth", "progress",
    "achieve", "win", "victory", "benefit", "advantage", "breakthrough",
    "discover", "launch", "celebrate", "strong", "powerful", "leading",
])

_NEGATIVE_EN = frozenset([
    "bad", "terrible", "awful", "horrible", "disaster", "fail", "failure",
    "negative", "problem", "crisis", "danger", "risk", "threat", "loss",
    "wrong", "worse", "worst", "decline", "crash", "collapse", "death",
    "war", "violence", "attack", "corruption", "scandal", "fraud",
    "arrest", "crime", "victim", "emergency", "catastrophe", "tragedy",
    "broke", "bankrupt", "collapse", "fire", "explosion",
])

_POSITIVE_AR = frozenset([
    "جيد", "ممتاز", "رائع", "مذهل", "نجاح", "ناجح", "سعيد", "فرح", "حب",
    "أفضل", "مثالي", "متميز", "استثنائي", "مبهر", "فعّال", "مبتكر",
    "تحسين", "نمو", "تقدم", "إنجاز", "انتصار", "فوز", "فائدة", "ميزة",
    "اكتشاف", "انطلاق", "احتفال", "قوي", "رائد", "إيجابي", "اختراق",
])

_NEGATIVE_AR = frozenset([
    "سيئ", "فظيع", "مروع", "كارثة", "فشل", "سلبي", "مشكلة", "أزمة",
    "خطر", "تهديد", "خسارة", "خطأ", "أسوأ", "تراجع", "انهيار", "وفاة",
    "حرب", "عنف", "هجوم", "فساد", "فضيحة", "احتيال", "اعتقال", "جريمة",
    "ضحية", "طوارئ", "كارثي", "مأساة", "إفلاس", "حريق", "انفجار",
])

_NEGATION_EN = frozenset(["not", "never", "no", "don't", "doesn't", "didn't", "cannot", "can't", "won't"])
_NEGATION_AR = frozenset(["لا", "لم", "لن", "ليس", "ما", "غير"])

_WORD_RE = re.compile(r"\b\w{2,}\b", re.UNICODE)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SentimentConfig:
    """إعدادات محلّل المشاعر."""

    title_boost: float = 1.5    # وزن العنوان مقارنة بالمحتوى
    negation_window: int = 3     # عدد الكلمات بعد الـ negation للتأثير
    positive_threshold: float = 0.1
    negative_threshold: float = -0.1
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SentimentResult:
    """نتيجة تحليل مشاعر مقال."""
    article_id: str
    label: str          # "positive" | "negative" | "neutral"
    compound: float     # [-1.0, +1.0]
    positive: float     # درجة الإيجابية [0, 1]
    negative: float     # درجة السلبية [0, 1]
    neutral: float      # درجة الحياد [0, 1]
    method: str = "lexicon"  # "vader" | "lexicon"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "compound": round(self.compound, 4),
            "positive": round(self.positive, 4),
            "negative": round(self.negative, 4),
            "neutral": round(self.neutral, 4),
            "method": self.method,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Lexicon-based scoring
# ─────────────────────────────────────────────────────────────────────────────

def _lexicon_score(
    text: str,
    language: str = "en",
    negation_window: int = 3,
) -> Tuple[float, float, float]:
    """حساب درجات الإيجابية والسلبية والحياد.

    Returns
    -------
    (positive, negative, neutral) — كل في [0, 1]، مجموعها = 1
    """
    pos_kws = _POSITIVE_AR if language == "ar" else _POSITIVE_EN
    neg_kws = _NEGATIVE_AR if language == "ar" else _NEGATIVE_EN
    neg_words = _NEGATION_AR if language == "ar" else _NEGATION_EN

    words = _WORD_RE.findall(text.lower())
    if not words:
        return 0.0, 0.0, 1.0

    pos_count = 0
    neg_count = 0
    negated = False
    neg_countdown = 0

    for i, word in enumerate(words):
        if word in neg_words:
            negated = True
            neg_countdown = negation_window
        elif neg_countdown > 0:
            neg_countdown -= 1
            if neg_countdown == 0:
                negated = False

        if word in pos_kws:
            if negated:
                neg_count += 1
            else:
                pos_count += 1
        elif word in neg_kws:
            if negated:
                pos_count += 1
            else:
                neg_count += 1

    total = pos_count + neg_count
    if total == 0:
        return 0.0, 0.0, 1.0

    pos_ratio = pos_count / (len(words) + 1)
    neg_ratio = neg_count / (len(words) + 1)
    total_ratio = pos_ratio + neg_ratio
    neutral = max(0.0, 1.0 - total_ratio)

    # تطبيع
    total_sum = pos_ratio + neg_ratio + neutral
    if total_sum > 0:
        pos_ratio /= total_sum
        neg_ratio /= total_sum
        neutral /= total_sum

    return round(pos_ratio, 4), round(neg_ratio, 4), round(neutral, 4)


def _compute_compound(positive: float, negative: float) -> float:
    """حساب درجة compound في [-1.0, +1.0]."""
    return round(positive - negative, 4)


# ─────────────────────────────────────────────────────────────────────────────
# VADER scoring
# ─────────────────────────────────────────────────────────────────────────────

_vader_analyzer: Optional[object] = None


def _get_vader():
    global _vader_analyzer
    if _vader_analyzer is None and _VADER_AVAILABLE:
        _vader_analyzer = SentimentIntensityAnalyzer()
    return _vader_analyzer


def _vader_score(text: str) -> Tuple[float, float, float, float]:
    """درجات VADER: (compound, positive, negative, neutral)."""
    analyzer = _get_vader()
    if analyzer is None:
        return 0.0, 0.0, 0.0, 1.0
    try:
        scores = analyzer.polarity_scores(text)
        return scores["compound"], scores["pos"], scores["neg"], scores["neu"]
    except Exception as exc:
        logger.debug("VADER error: %s", exc)
        return 0.0, 0.0, 0.0, 1.0


# ─────────────────────────────────────────────────────────────────────────────
# SentimentAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class SentimentAnalyzer:
    """محلّل مشاعر يدعم العربية والإنجليزية.

    يستخدم VADER للإنجليزية إذا توفّر، وقاموس مخصص للعربية.

    Parameters
    ----------
    config:
        SentimentConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[SentimentConfig] = None) -> None:
        self.config = config or SentimentConfig()

    def analyze_text(
        self,
        text: str,
        title: str = "",
        language: str = "en",
    ) -> SentimentResult:
        """تحليل مشاعر نص.

        Parameters
        ----------
        text:
            المحتوى الرئيسي.
        title:
            العنوان (يُضاف بترجيح أعلى).
        language:
            اللغة.

        Returns
        -------
        SentimentResult.
        """
        cfg = self.config
        combined = (title + " ") * int(cfg.title_boost) + text

        if _VADER_AVAILABLE and language != "ar":
            compound, pos, neg, neu = _vader_score(combined)
            method = "vader"
        else:
            pos, neg, neu = _lexicon_score(
                combined, language=language, negation_window=cfg.negation_window
            )
            compound = _compute_compound(pos, neg)
            method = "lexicon"

        # تحديد التسمية
        if compound >= cfg.positive_threshold:
            label = "positive"
        elif compound <= cfg.negative_threshold:
            label = "negative"
        else:
            label = "neutral"

        return SentimentResult(
            article_id="",
            label=label,
            compound=compound,
            positive=pos,
            negative=neg,
            neutral=neu,
            method=method,
        )

    def analyze_article(self, article: Article) -> SentimentResult:
        """تحليل مشاعر مقال.

        Parameters
        ----------
        article:
            المقال المصدر.

        Returns
        -------
        SentimentResult.
        """
        lang = article.metadata.language or "en"
        result = self.analyze_text(
            text=article.content,
            title=article.title,
            language=lang,
        )
        result.article_id = article.id
        return result

    def enrich_article(self, article: Article) -> Article:
        """إضافة بيانات المشاعر إلى metadata.extra.

        Returns
        -------
        New Article مع بيانات المشاعر.
        """
        result = self.analyze_article(article)

        new_extra = dict(article.metadata.extra)
        new_extra["sentiment"] = result.to_dict()

        new_meta = article.metadata.model_copy(update={"extra": new_extra})
        enriched = article.model_copy(update={"metadata": new_meta})

        logger.debug(
            "SentimentAnalyzer: id=%s label=%s compound=%.3f",
            article.id,
            result.label,
            result.compound,
        )
        return enriched

    def enrich_batch(self, articles: List[Article]) -> List[Article]:
        """تحليل مشاعر دُفعة من المقالات.

        Returns
        -------
        List of enriched Article copies.
        """
        result = [self.enrich_article(a) for a in articles]
        labels = [a.metadata.extra.get("sentiment", {}).get("label", "?") for a in result]
        pos = labels.count("positive")
        neg = labels.count("negative")
        neu = labels.count("neutral")
        logger.info(
            "SentimentAnalyzer.enrich_batch: processed=%d positive=%d negative=%d neutral=%d",
            len(result), pos, neg, neu,
        )
        return result
