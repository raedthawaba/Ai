"""Topic Classifier — Phase 2 (Section 2.4).

تصنيف موضوعي بدون نماذج ML ثقيلة.

الطريقة:
- قاموس keywords لكل موضوع (عربي + إنجليزي)
- TF-IDF بسيط (keyword density)
- Multi-label classification (مقال قد ينتمي لأكثر من موضوع)
- درجات ثقة مُحسوبة

المواضيع المدعومة:
سياسة، اقتصاد، تقنية، رياضة، صحة، علوم، ترفيه،
أعمال، تعليم، بيئة، دين، ثقافة، أمن، طقس، منوعات
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Topic keyword dictionaries
# ─────────────────────────────────────────────────────────────────────────────

_TOPICS: Dict[str, Dict[str, List[str]]] = {
    "technology": {
        "en": ["artificial intelligence", "machine learning", "software", "technology",
               "digital", "internet", "computer", "programming", "data", "cloud",
               "cybersecurity", "blockchain", "startup", "app", "mobile", "AI", "robot",
               "algorithm", "database", "network", "developer", "code", "tech"],
        "ar": ["ذكاء اصطناعي", "برمجة", "تقنية", "تكنولوجيا", "إنترنت", "حاسوب",
               "بيانات", "سحابة", "أمن إلكتروني", "بلوكتشين", "تطبيق", "روبوت",
               "خوارزمية", "شبكة", "مطور", "رقمي", "ذكاء", "تقني"],
    },
    "politics": {
        "en": ["government", "election", "president", "minister", "parliament",
               "democracy", "policy", "senate", "congress", "vote", "political",
               "opposition", "ruling", "treaty", "sanctions", "diplomacy", "war",
               "peace", "leader", "campaign", "legislation"],
        "ar": ["حكومة", "انتخابات", "رئيس", "وزير", "برلمان", "ديمقراطية",
               "سياسة", "تصويت", "معارضة", "دبلوماسية", "حرب", "سلام",
               "قانون", "اتفاقية", "عقوبات", "قيادة", "حزب", "سياسي"],
    },
    "economy": {
        "en": ["economy", "market", "stock", "finance", "investment", "gdp", "inflation",
               "bank", "currency", "trade", "recession", "budget", "revenue", "growth",
               "profit", "shares", "interest rate", "bond", "commodity", "oil", "gold"],
        "ar": ["اقتصاد", "سوق", "بورصة", "مالية", "استثمار", "تضخم", "بنك",
               "عملة", "تجارة", "ميزانية", "نمو", "ربح", "أسهم", "نفط", "ذهب",
               "فائدة", "سندات", "إيرادات", "ناتج محلي"],
    },
    "sports": {
        "en": ["football", "soccer", "basketball", "tennis", "olympics", "athlete",
               "championship", "league", "tournament", "coach", "player", "goal",
               "score", "game", "match", "team", "stadium", "sports", "race"],
        "ar": ["كرة قدم", "كرة السلة", "تنس", "أولمبياد", "بطولة", "دوري",
               "مباراة", "لاعب", "هدف", "فريق", "ملعب", "رياضة", "مدرب",
               "بطل", "سباق", "أبطال"],
    },
    "health": {
        "en": ["health", "medicine", "disease", "hospital", "doctor", "treatment",
               "vaccine", "virus", "cancer", "diabetes", "mental health", "surgery",
               "drug", "pharmacy", "patient", "clinical", "therapy", "nutrition"],
        "ar": ["صحة", "طب", "مرض", "مستشفى", "طبيب", "علاج", "لقاح", "فيروس",
               "سرطان", "سكري", "صحة نفسية", "عملية", "دواء", "مريض", "سريري",
               "تغذية", "علاج طبيعي"],
    },
    "science": {
        "en": ["science", "research", "discovery", "space", "nasa", "climate",
               "environment", "physics", "biology", "chemistry", "experiment",
               "universe", "planet", "genome", "evolution", "quantum"],
        "ar": ["علوم", "بحث", "اكتشاف", "فضاء", "ناسا", "مناخ", "بيئة",
               "فيزياء", "أحياء", "كيمياء", "تجربة", "كون", "كوكب", "جينوم",
               "تطور", "كمي"],
    },
    "business": {
        "en": ["company", "business", "startup", "entrepreneur", "corporate", "ceo",
               "merger", "acquisition", "ipo", "profit", "revenue", "brand", "marketing",
               "strategy", "industry", "enterprise", "retail", "e-commerce"],
        "ar": ["شركة", "أعمال", "مؤسسة", "رائد أعمال", "شركات", "رئيس تنفيذي",
               "اندماج", "استحواذ", "ربح", "إيرادات", "علامة تجارية", "تسويق",
               "استراتيجية", "تجارة إلكترونية", "صناعة"],
    },
    "education": {
        "en": ["education", "school", "university", "student", "teacher", "learning",
               "curriculum", "degree", "scholarship", "research", "academy", "training",
               "study", "graduate", "college", "professor"],
        "ar": ["تعليم", "مدرسة", "جامعة", "طالب", "معلم", "تعلم", "منهج",
               "شهادة", "منحة", "أكاديمية", "تدريب", "دراسة", "تخرج", "كلية",
               "أستاذ", "بحث علمي"],
    },
    "entertainment": {
        "en": ["movie", "film", "music", "celebrity", "actor", "singer", "award",
               "oscar", "grammy", "concert", "album", "series", "television", "streaming",
               "hollywood", "entertainment", "fashion", "art"],
        "ar": ["فيلم", "موسيقى", "مشهور", "ممثل", "مغني", "جائزة", "حفل",
               "ألبوم", "مسلسل", "تلفزيون", "ترفيه", "فن", "أزياء", "سينما"],
    },
    "security": {
        "en": ["security", "terrorism", "attack", "military", "defense", "hacking",
               "cybercrime", "surveillance", "intelligence", "threat", "conflict",
               "war", "weapon", "army", "police", "crime"],
        "ar": ["أمن", "إرهاب", "هجوم", "عسكري", "دفاع", "اختراق", "جريمة إلكترونية",
               "استخبارات", "تهديد", "نزاع", "سلاح", "جيش", "شرطة", "جريمة"],
    },
}

_WORD_RE = re.compile(r"\b\w{2,}\b", re.UNICODE)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TopicClassifierConfig:
    """إعدادات مصنّف المواضيع."""

    min_score: float = 0.05            # حد أدنى للثقة لتصنيف موضوع
    max_topics: int = 3                # عدد مواضيع أقصى لكل مقال
    title_boost: float = 2.0           # وزن العنوان مقارنة بالمحتوى
    use_ngrams: bool = True            # البحث بـ n-grams (عبارات)
    fallback_topic: str = "general"    # الموضوع الافتراضي عند عدم اليقين
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Topic Classification Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TopicScore:
    """موضوع واحد مع درجة ثقته."""
    topic: str
    score: float
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    """نتيجة تصنيف مقال."""
    article_id: str
    primary_topic: str
    topics: List[TopicScore] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def topic_names(self) -> List[str]:
        return [t.topic for t in self.topics]


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_density_score(
    text: str,
    keywords: List[str],
    word_count: int,
    use_ngrams: bool = True,
) -> Tuple[float, List[str]]:
    """حساب كثافة الكلمات المفتاحية في النص.

    Returns
    -------
    (score, matched_keywords)
    """
    if not text or word_count == 0:
        return 0.0, []

    lower_text = text.lower()
    matched = []
    total_hits = 0

    for kw in keywords:
        kw_lower = kw.lower()
        if use_ngrams and " " in kw:
            count = lower_text.count(kw_lower)
        else:
            count = len(re.findall(r"\b" + re.escape(kw_lower) + r"\b", lower_text))

        if count > 0:
            matched.append(kw)
            total_hits += count

    # درجة = مجموع الضربات / (عدد الكلمات + 1)، مُقيّدة بـ 1.0
    score = math.log1p(total_hits) / math.log1p(word_count + 1)
    return min(score, 1.0), matched


# ─────────────────────────────────────────────────────────────────────────────
# TopicClassifier
# ─────────────────────────────────────────────────────────────────────────────

class TopicClassifier:
    """مصنّف مواضيع بسيط قائم على قاموس الكلمات المفتاحية.

    Parameters
    ----------
    config:
        TopicClassifierConfig للتحكم في السلوك.
    custom_topics:
        قاموس مواضيع إضافية: {"topic_name": {"ar": [...], "en": [...]}}
    """

    def __init__(
        self,
        config: Optional[TopicClassifierConfig] = None,
        custom_topics: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> None:
        self.config = config or TopicClassifierConfig()
        self._topics = dict(_TOPICS)
        if custom_topics:
            self._topics.update(custom_topics)

    def classify_text(
        self,
        text: str,
        title: str = "",
        language: str = "en",
    ) -> List[TopicScore]:
        """تصنيف نص إلى مواضيع.

        Parameters
        ----------
        text:
            المحتوى الرئيسي.
        title:
            العنوان (يحصل على boost).
        language:
            اللغة لاختيار قاموس الكلمات المناسب.

        Returns
        -------
        قائمة TopicScore مُرتّبة تنازلياً.
        """
        cfg = self.config
        lang_key = "ar" if language == "ar" else "en"

        # دمج العنوان + المحتوى مع ترجيح العنوان
        combined = title * int(cfg.title_boost) + " " + text
        word_count = max(1, len(_WORD_RE.findall(combined)))

        topic_scores: List[TopicScore] = []
        for topic_name, lang_dict in self._topics.items():
            keywords = lang_dict.get(lang_key, []) + lang_dict.get(
                "ar" if lang_key == "en" else "en", []
            )
            if not keywords:
                continue

            score, matched = _keyword_density_score(
                combined, keywords, word_count, use_ngrams=cfg.use_ngrams
            )

            if score >= cfg.min_score:
                topic_scores.append(TopicScore(
                    topic=topic_name,
                    score=round(score, 4),
                    matched_keywords=matched[:5],  # أهم 5 كلمات مفتاحية
                ))

        # ترتيب تنازلي وأخذ الأعلى
        topic_scores.sort(key=lambda t: t.score, reverse=True)
        return topic_scores[: cfg.max_topics]

    def classify_article(self, article: Article) -> ClassificationResult:
        """تصنيف مقال.

        Parameters
        ----------
        article:
            المقال المصدر.

        Returns
        -------
        ClassificationResult.
        """
        lang = article.metadata.language or "en"
        topics = self.classify_text(
            text=article.content,
            title=article.title,
            language=lang,
        )

        primary = topics[0].topic if topics else self.config.fallback_topic
        confidence = topics[0].score if topics else 0.0

        return ClassificationResult(
            article_id=article.id,
            primary_topic=primary,
            topics=topics,
            confidence=confidence,
        )

    def enrich_article(self, article: Article) -> Article:
        """إضافة تصنيفات المواضيع إلى metadata.extra.

        Returns
        -------
        New Article مع بيانات المواضيع.
        """
        result = self.classify_article(article)

        new_extra = dict(article.metadata.extra)
        new_extra["topics"] = [
            {"topic": t.topic, "score": t.score}
            for t in result.topics
        ]
        new_extra["primary_topic"] = result.primary_topic
        new_extra["topic_confidence"] = result.confidence

        # إضافة الموضوع الرئيسي كـ tag
        new_tags = list(article.metadata.tags)
        if result.primary_topic and result.primary_topic not in new_tags:
            new_tags.append(result.primary_topic)

        new_meta = article.metadata.model_copy(update={
            "extra": new_extra,
            "tags": new_tags,
        })
        enriched = article.model_copy(update={"metadata": new_meta})

        logger.debug(
            "TopicClassifier: id=%s primary=%s confidence=%.3f",
            article.id,
            result.primary_topic,
            result.confidence,
        )
        return enriched

    def enrich_batch(self, articles: List[Article]) -> List[Article]:
        """تصنيف دُفعة من المقالات.

        Returns
        -------
        List of enriched Article copies.
        """
        result = [self.enrich_article(a) for a in articles]
        logger.info("TopicClassifier.enrich_batch: processed=%d", len(result))
        return result
