"""Cleaning Pipeline — Phase 2 (Section 2.2).

نظام تنظيف احترافي موحّد يجمع:
  - HTMLCleaner   : إزالة HTML وإعلانات وسكريبتات
  - TextCleaner   : تنظيف النص + إزالة URLs والبريد والمذكورات
  - TextNormalizer: Unicode + emoji + علامات ترقيم + عربي موسّع

إضافات Phase 2:
  - BoilerplateRemover  : إزالة محتوى القوالب المكررة
  - DuplicateParagraphFilter: إزالة الفقرات المكررة
  - CleaningMetrics     : قياس جودة التنظيف
  - CleaningPipeline    : واجهة موحّدة async-safe
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from shared.schemas.article import Article
from .html_cleaner import HTMLCleaner
from .text_cleaner import TextCleaner, CleanerConfig
from .text_normalizer import TextNormalizer, NormalizerConfig

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Boilerplate patterns (عبارات قوالب شائعة في صفحات الويب)
# ─────────────────────────────────────────────────────────────────────────────

_BOILERPLATE_PATTERNS_EN = [
    r"subscribe to our newsletter",
    r"follow us on (twitter|facebook|instagram|linkedin)",
    r"all rights reserved",
    r"copyright \d{4}",
    r"(click|tap) here to (read|view|see) more",
    r"(read|view) more articles?",
    r"this (article|content|post) (is|was) (originally )?published",
    r"share this (article|post|story|content)",
    r"(leave|write|add) a (comment|reply)",
    r"cookies? policy",
    r"privacy policy",
    r"terms (of service|and conditions)",
    r"advertisement",
    r"sponsored (by|content)",
    r"(sign|log) in (to|with)",
    r"create an? account",
    r"download (the )?(app|application)",
]

_BOILERPLATE_PATTERNS_AR = [
    r"اشترك في نشرتنا الإخبارية",
    r"تابعنا على (تويتر|فيسبوك|إنستغرام|لينكدإن)",
    r"جميع الحقوق محفوظة",
    r"(اضغط|انقر) هنا للمزيد",
    r"قراءة المزيد",
    r"شارك هذا المقال",
    r"أضف تعليقاً",
    r"سياسة الخصوصية",
    r"اتفاقية الاستخدام",
    r"إعلان",
    r"محتوى مدعوم",
    r"سجّل الدخول",
    r"إنشاء حساب",
    r"حمّل التطبيق",
]

_BOILERPLATE_RE_EN = re.compile(
    "|".join(_BOILERPLATE_PATTERNS_EN), re.IGNORECASE
)
_BOILERPLATE_RE_AR = re.compile(
    "|".join(_BOILERPLATE_PATTERNS_AR), re.UNICODE
)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CleaningPipelineConfig:
    """إعدادات Cleaning Pipeline الموحّد."""

    # تفعيل / تعطيل المراحل
    use_html_cleaner: bool = True
    use_text_cleaner: bool = True
    use_normalizer: bool = True
    remove_boilerplate: bool = True
    remove_duplicate_paragraphs: bool = True

    # إعدادات TextCleaner
    cleaner_config: Optional[CleanerConfig] = None
    normalizer_config: Optional[NormalizerConfig] = None

    # حد أدنى للمحتوى بعد التنظيف
    min_content_length: int = 20

    # Boilerplate sentence-level threshold
    max_boilerplate_ratio: float = 0.4  # إذا > 40% من الجمل boilerplate → رفض

    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# CleaningMetrics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CleaningMetrics:
    """قياسات جودة التنظيف لكل مقال."""

    article_id: str
    original_content_len: int = 0
    cleaned_content_len: int = 0
    html_removed: bool = False
    boilerplate_removed: int = 0
    duplicate_paragraphs_removed: int = 0
    urls_removed: int = 0
    emails_removed: int = 0
    duration_ms: float = 0.0
    rejected: bool = False
    rejection_reason: Optional[str] = None

    @property
    def reduction_ratio(self) -> float:
        """نسبة الحذف = (original - cleaned) / original."""
        if self.original_content_len == 0:
            return 0.0
        return max(0.0, 1.0 - self.cleaned_content_len / self.original_content_len)

    @property
    def content_retained_ratio(self) -> float:
        """نسبة المحتوى المحتفظ به."""
        return 1.0 - self.reduction_ratio

    def to_dict(self) -> dict:
        return {
            "article_id": self.article_id,
            "original_len": self.original_content_len,
            "cleaned_len": self.cleaned_content_len,
            "reduction_ratio": round(self.reduction_ratio, 4),
            "html_removed": self.html_removed,
            "boilerplate_removed": self.boilerplate_removed,
            "dup_paragraphs_removed": self.duplicate_paragraphs_removed,
            "duration_ms": round(self.duration_ms, 2),
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class BatchCleaningMetrics:
    """إحصائيات تنظيف دُفعة كاملة."""

    total_input: int = 0
    total_cleaned: int = 0
    total_rejected: int = 0
    total_duration_ms: float = 0.0
    article_metrics: List[CleaningMetrics] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        return self.total_rejected / self.total_input if self.total_input else 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total_input if self.total_input else 0.0

    @property
    def avg_reduction_ratio(self) -> float:
        if not self.article_metrics:
            return 0.0
        return sum(m.reduction_ratio for m in self.article_metrics) / len(self.article_metrics)


# ─────────────────────────────────────────────────────────────────────────────
# Boilerplate Remover
# ─────────────────────────────────────────────────────────────────────────────

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟\n])\s+")
_PARA_SPLIT = re.compile(r"\n{2,}")


def _remove_boilerplate_sentences(
    text: str,
    language: str = "en",
    max_ratio: float = 0.4,
) -> Tuple[str, int]:
    """إزالة جمل القوالب من النص.

    Returns
    -------
    (cleaned_text, num_removed)
    """
    sentences = _SENTENCE_SPLIT.split(text.strip())
    if not sentences:
        return text, 0

    pattern = _BOILERPLATE_RE_AR if language == "ar" else _BOILERPLATE_RE_EN

    clean_sentences = []
    removed = 0
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if pattern.search(sent):
            removed += 1
        else:
            clean_sentences.append(sent)

    # إذا تجاوزنا النسبة المقبولة → نُعيد النص الأصلي
    total = len(clean_sentences) + removed
    if total > 0 and removed / total > max_ratio:
        logger.debug("boilerplate_remover: نسبة عالية جداً (%d/%d) — الاحتفاظ بالأصل", removed, total)
        return text, 0

    return " ".join(clean_sentences), removed


def _remove_duplicate_paragraphs(text: str) -> Tuple[str, int]:
    """إزالة الفقرات المكررة بشكل متتابع.

    Returns
    -------
    (cleaned_text, num_removed)
    """
    paragraphs = _PARA_SPLIT.split(text.strip())
    seen_hashes: set = set()
    unique_paras = []
    removed = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # تطبيع قبل التجزئة
        norm = re.sub(r"\s+", " ", para.lower())
        h = hashlib.md5(norm.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            removed += 1
        else:
            seen_hashes.add(h)
            unique_paras.append(para)

    return "\n\n".join(unique_paras), removed


# ─────────────────────────────────────────────────────────────────────────────
# URL / Email counter helpers
# ─────────────────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", re.UNICODE)


def _count_urls(text: str) -> int:
    return len(_URL_RE.findall(text))


def _count_emails(text: str) -> int:
    return len(_EMAIL_RE.findall(text))


# ─────────────────────────────────────────────────────────────────────────────
# CleaningPipeline
# ─────────────────────────────────────────────────────────────────────────────

class CleaningPipeline:
    """Pipeline تنظيف موحّد وآمن للاستخدام sync/async.

    المراحل (بالترتيب):
    1. HTMLCleaner   — إزالة HTML وإعلانات وسكريبتات
    2. TextCleaner   — إزالة URLs والبريد والتنظيف الأساسي
    3. TextNormalizer— Unicode وemoji وعربي موسّع
    4. BoilerplateRemover — إزالة جمل القوالب
    5. DuplicateParagraphFilter — إزالة الفقرات المكررة

    Parameters
    ----------
    config:
        CleaningPipelineConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[CleaningPipelineConfig] = None) -> None:
        self.config = config or CleaningPipelineConfig()
        self._html_cleaner = HTMLCleaner(use_trafilatura=True)
        self._text_cleaner = TextCleaner(self.config.cleaner_config)
        self._normalizer = TextNormalizer(self.config.normalizer_config)

    # ─── Sync API ──────────────────────────────────────────────────────────

    def clean_article(self, article: Article) -> Tuple[Article, CleaningMetrics]:
        """تنظيف مقال واحد.

        Returns
        -------
        (cleaned_article, metrics)
        """
        cfg = self.config
        start = time.monotonic()
        metrics = CleaningMetrics(
            article_id=article.id,
            original_content_len=len(article.content),
        )

        try:
            cleaned = article
            lang = article.metadata.language or "en"

            # 1. HTMLCleaner
            if cfg.use_html_cleaner:
                before = len(cleaned.content)
                cleaned = self._html_cleaner.clean_article(cleaned)
                metrics.html_removed = len(cleaned.content) < before

            # 2. TextCleaner
            if cfg.use_text_cleaner:
                metrics.urls_removed = _count_urls(cleaned.content)
                metrics.emails_removed = _count_emails(cleaned.content)
                cleaned = self._text_cleaner.clean_article(cleaned)

            # 3. TextNormalizer
            if cfg.use_normalizer:
                cleaned = self._normalizer.normalize_article(cleaned)

            # 4. Boilerplate removal
            if cfg.remove_boilerplate and cleaned.content:
                new_content, removed_count = _remove_boilerplate_sentences(
                    cleaned.content,
                    language=lang,
                    max_ratio=cfg.max_boilerplate_ratio,
                )
                if removed_count > 0 and new_content.strip():
                    cleaned = cleaned.model_copy(update={"content": new_content})
                    metrics.boilerplate_removed = removed_count

            # 5. Duplicate paragraph removal
            if cfg.remove_duplicate_paragraphs and cleaned.content:
                new_content, dup_count = _remove_duplicate_paragraphs(cleaned.content)
                if dup_count > 0 and new_content.strip():
                    cleaned = cleaned.model_copy(update={"content": new_content})
                    metrics.duplicate_paragraphs_removed = dup_count

            # التحقق من الحد الأدنى للمحتوى
            final_len = len(cleaned.content.strip())
            metrics.cleaned_content_len = final_len

            if final_len < cfg.min_content_length:
                metrics.rejected = True
                metrics.rejection_reason = (
                    f"content_too_short_after_cleaning "
                    f"(len={final_len} min={cfg.min_content_length})"
                )
                logger.debug(
                    "CleaningPipeline: rejected id=%s reason=%s",
                    article.id,
                    metrics.rejection_reason,
                )

        except Exception as exc:
            logger.error("CleaningPipeline: error cleaning id=%s — %s", article.id, exc)
            cleaned = article  # استرجاع المقال الأصلي
            metrics.rejected = False
            metrics.cleaned_content_len = len(article.content)

        metrics.duration_ms = (time.monotonic() - start) * 1000
        return cleaned, metrics

    def clean_batch(
        self, articles: List[Article]
    ) -> Tuple[List[Article], BatchCleaningMetrics]:
        """تنظيف دُفعة من المقالات.

        Returns
        -------
        (cleaned_articles, batch_metrics)
        """
        batch_metrics = BatchCleaningMetrics(total_input=len(articles))
        cleaned_articles: List[Article] = []

        for article in articles:
            cleaned, metrics = self.clean_article(article)
            batch_metrics.article_metrics.append(metrics)
            batch_metrics.total_duration_ms += metrics.duration_ms

            if not metrics.rejected:
                cleaned_articles.append(cleaned)
                batch_metrics.total_cleaned += 1
            else:
                batch_metrics.total_rejected += 1

        logger.info(
            "CleaningPipeline.clean_batch: in=%d cleaned=%d rejected=%d "
            "avg_reduction=%.1f%% avg_time=%.1fms",
            batch_metrics.total_input,
            batch_metrics.total_cleaned,
            batch_metrics.total_rejected,
            batch_metrics.avg_reduction_ratio * 100,
            batch_metrics.avg_duration_ms,
        )
        return cleaned_articles, batch_metrics

    # ─── Async API ─────────────────────────────────────────────────────────

    async def async_clean_article(
        self, article: Article
    ) -> Tuple[Article, CleaningMetrics]:
        """تنظيف مقال واحد بشكل async (I/O-safe)."""
        return await asyncio.to_thread(self.clean_article, article)

    async def async_clean_batch(
        self, articles: List[Article], max_concurrency: int = 10
    ) -> Tuple[List[Article], BatchCleaningMetrics]:
        """تنظيف دُفعة من المقالات بالتوازي."""
        sem = asyncio.Semaphore(max_concurrency)

        async def _clean_one(a: Article) -> Tuple[Article, CleaningMetrics]:
            async with sem:
                return await self.async_clean_article(a)

        results = await asyncio.gather(*[_clean_one(a) for a in articles])

        batch_metrics = BatchCleaningMetrics(total_input=len(articles))
        cleaned_articles: List[Article] = []

        for cleaned, metrics in results:
            batch_metrics.article_metrics.append(metrics)
            batch_metrics.total_duration_ms += metrics.duration_ms
            if not metrics.rejected:
                cleaned_articles.append(cleaned)
                batch_metrics.total_cleaned += 1
            else:
                batch_metrics.total_rejected += 1

        logger.info(
            "CleaningPipeline.async_clean_batch: in=%d cleaned=%d rejected=%d",
            batch_metrics.total_input,
            batch_metrics.total_cleaned,
            batch_metrics.total_rejected,
        )
        return cleaned_articles, batch_metrics
