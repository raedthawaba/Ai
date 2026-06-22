"""Filtering Pipeline — Phase 2 (Section 2.3).

Pipeline موحّد يجمع جميع طبقات الفلترة:
  1. ContentFilter    — حد أدنى/أقصى للمحتوى، كلمات محجوبة/مطلوبة
  2. PolicyFilter     — قواعد المشروع (domains, keywords, min_length)
  3. LanguageFilter   — كشف اللغة والفلترة
  4. QualityScorer    — درجة الجودة
  5. SpamDetector     — كشف البريد المزعج
  6. Deduplicator     — منع التكرار
  7. PIIFilter        — إخفاء البيانات الحساسة

يُعيد FilteringMetrics شاملة لكل دُفعة.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article
from .content_filter import ContentFilter, FilterConfig
from .policy_filter import PolicyFilter, PolicyFilterConfig
from .language_filter import LanguageFilter, LanguageFilterConfig
from .quality_scorer import QualityScorer, QualityScorerConfig
from .spam_detector import SpamDetector, SpamDetectorConfig
from .deduplicator import Deduplicator, DeduplicatorConfig
from .pii_filter import PIIFilter, PIIFilterConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FilteringPipelineConfig:
    """إعدادات Filtering Pipeline الموحّد."""

    # تفعيل / تعطيل كل طبقة
    use_content_filter: bool = True
    use_policy_filter: bool = True
    use_language_filter: bool = True
    use_quality_scorer: bool = True
    use_spam_detector: bool = True
    use_deduplicator: bool = True
    use_pii_filter: bool = True

    # إعدادات كل طبقة
    content_config: Optional[FilterConfig] = None
    policy_config: Optional[PolicyFilterConfig] = None
    language_config: Optional[LanguageFilterConfig] = None
    quality_config: Optional[QualityScorerConfig] = None
    spam_config: Optional[SpamDetectorConfig] = None
    dedup_config: Optional[DeduplicatorConfig] = None
    pii_config: Optional[PIIFilterConfig] = None

    # إيقاف الـ pipeline عند أول رفض لكل مقال
    fail_fast: bool = True

    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Filtering Metrics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArticleFilterResult:
    """نتيجة فلترة مقال واحد."""
    article_id: str
    passed: bool
    rejection_reason: Optional[str] = None
    rejected_by: Optional[str] = None  # اسم الطبقة التي رفضت المقال
    quality_score: float = 0.0
    is_spam: bool = False
    is_duplicate: bool = False
    pii_count: int = 0
    language: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class FilteringMetrics:
    """إحصائيات فلترة دُفعة كاملة."""
    total_input: int = 0
    total_passed: int = 0
    total_rejected: int = 0
    rejections_by_layer: Dict[str, int] = field(default_factory=dict)
    total_pii_redacted: int = 0
    total_spam_detected: int = 0
    total_duplicates: int = 0
    total_duration_ms: float = 0.0
    article_results: List[ArticleFilterResult] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        return self.total_rejected / self.total_input if self.total_input else 0.0

    @property
    def avg_quality_score(self) -> float:
        scores = [r.quality_score for r in self.article_results if r.passed]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict:
        return {
            "total_input": self.total_input,
            "total_passed": self.total_passed,
            "total_rejected": self.total_rejected,
            "rejection_rate": round(self.rejection_rate, 4),
            "rejections_by_layer": self.rejections_by_layer,
            "total_pii_redacted": self.total_pii_redacted,
            "total_spam_detected": self.total_spam_detected,
            "total_duplicates": self.total_duplicates,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "avg_quality_score": round(self.avg_quality_score, 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# FilteringPipeline
# ─────────────────────────────────────────────────────────────────────────────

class FilteringPipeline:
    """Pipeline فلترة موحّد يُطبّق جميع طبقات الجودة والأمان.

    Parameters
    ----------
    config:
        FilteringPipelineConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[FilteringPipelineConfig] = None) -> None:
        self.config = config or FilteringPipelineConfig()
        self._init_filters()

    def _init_filters(self) -> None:
        cfg = self.config
        self._content_filter = ContentFilter(cfg.content_config) if cfg.use_content_filter else None
        self._policy_filter = PolicyFilter(cfg.policy_config) if cfg.use_policy_filter else None
        self._language_filter = LanguageFilter(cfg.language_config) if cfg.use_language_filter else None
        self._quality_scorer = QualityScorer(cfg.quality_config) if cfg.use_quality_scorer else None
        self._spam_detector = SpamDetector(cfg.spam_config) if cfg.use_spam_detector else None
        self._deduplicator = Deduplicator(cfg.dedup_config) if cfg.use_deduplicator else None
        self._pii_filter = PIIFilter(cfg.pii_config) if cfg.use_pii_filter else None

    def reset_dedup(self) -> None:
        """إعادة تعيين حالة الـ deduplication."""
        if self._deduplicator:
            self._deduplicator.reset()

    # ─── Article-level filtering ───────────────────────────────────────────

    def filter_article(
        self, article: Article
    ) -> Tuple[Optional[Article], ArticleFilterResult]:
        """فلترة مقال واحد عبر جميع الطبقات.

        Returns
        -------
        (filtered_article_or_None, result)
        """
        cfg = self.config
        start = time.monotonic()
        result = ArticleFilterResult(article_id=article.id, passed=True)
        current = article

        try:
            # 1. ContentFilter
            if self._content_filter:
                check_result = self._content_filter._check(current, update_state=True)
                if check_result:
                    result.passed = False
                    result.rejected_by = "ContentFilter"
                    result.rejection_reason = check_result
                    if cfg.fail_fast:
                        result.duration_ms = (time.monotonic() - start) * 1000
                        return None, result

            # 2. PolicyFilter
            if self._policy_filter and result.passed:
                policy_result = self._policy_filter.check_article(current)
                if not policy_result.passes:
                    result.passed = False
                    result.rejected_by = "PolicyFilter"
                    result.rejection_reason = policy_result.rejection_reason
                    if cfg.fail_fast:
                        result.duration_ms = (time.monotonic() - start) * 1000
                        return None, result

            # 3. LanguageFilter (tag language but keep all)
            if self._language_filter and result.passed:
                lang_result = self._language_filter._detect(current)
                result.language = lang_result.language
                # Update article metadata if language detected
                if lang_result.language and lang_result.language != "unknown":
                    try:
                        new_meta = current.metadata.model_copy(
                            update={"language": lang_result.language}
                        )
                        current = current.model_copy(update={"metadata": new_meta})
                    except Exception:
                        pass

                # Check if language is allowed
                lang_cfg = self.config.language_config
                if lang_cfg and lang_cfg.allowed_languages:
                    if lang_result.language not in lang_cfg.allowed_languages:
                        result.passed = False
                        result.rejected_by = "LanguageFilter"
                        result.rejection_reason = (
                            f"language_not_allowed ({lang_result.language})"
                        )
                        if cfg.fail_fast:
                            result.duration_ms = (time.monotonic() - start) * 1000
                            return None, result

            # 4. QualityScorer
            if self._quality_scorer and result.passed:
                score = self._quality_scorer.score_article(current)
                result.quality_score = score.total_score
                if not score.passes:
                    result.passed = False
                    result.rejected_by = "QualityScorer"
                    result.rejection_reason = score.rejection_reason
                    if cfg.fail_fast:
                        result.duration_ms = (time.monotonic() - start) * 1000
                        return None, result

            # 5. SpamDetector
            if self._spam_detector and result.passed:
                spam_result = self._spam_detector.detect(current)
                result.is_spam = spam_result.is_spam
                if spam_result.is_spam:
                    result.passed = False
                    result.rejected_by = "SpamDetector"
                    triggered = getattr(spam_result, "triggered_rules", [])
                    result.rejection_reason = f"spam ({', '.join(triggered)})" if triggered else "spam_detected"
                    if cfg.fail_fast:
                        result.duration_ms = (time.monotonic() - start) * 1000
                        return None, result

            # 6. Deduplicator (check only — batch dedup done in filter_batch)
            if self._deduplicator and result.passed:
                is_dup = self._deduplicator.is_duplicate(current)
                result.is_duplicate = is_dup
                if is_dup:
                    result.passed = False
                    result.rejected_by = "Deduplicator"
                    result.rejection_reason = "duplicate_content"
                    if cfg.fail_fast:
                        result.duration_ms = (time.monotonic() - start) * 1000
                        return None, result

            # 7. PIIFilter
            if self._pii_filter and result.passed:
                redacted, pii_result = self._pii_filter.apply_to_article(current)
                result.pii_count = pii_result.total_redacted
                if not pii_result.passed:
                    result.passed = False
                    result.rejected_by = "PIIFilter"
                    result.rejection_reason = pii_result.rejection_reason
                else:
                    current = redacted  # استخدام المقال المُنقّى

        except Exception as exc:
            logger.error(
                "FilteringPipeline: خطأ غير متوقع article_id=%s — %s",
                article.id, exc,
            )
            # نُبقي المقال في حالة passed لمنع crash الـ pipeline
            result.passed = True

        result.duration_ms = (time.monotonic() - start) * 1000
        return (current if result.passed else None), result

    # ─── Batch filtering ───────────────────────────────────────────────────

    def filter_batch(
        self, articles: List[Article], reset_dedup: bool = False
    ) -> Tuple[List[Article], FilteringMetrics]:
        """فلترة دُفعة من المقالات.

        Parameters
        ----------
        articles:
            قائمة المقالات.
        reset_dedup:
            إعادة تعيين dedup state قبل المعالجة.

        Returns
        -------
        (kept_articles, metrics)
        """
        if reset_dedup and self._deduplicator:
            self._deduplicator.reset()

        metrics = FilteringMetrics(total_input=len(articles))
        kept: List[Article] = []

        for article in articles:
            filtered_article, result = self.filter_article(article)
            metrics.article_results.append(result)
            metrics.total_duration_ms += result.duration_ms
            metrics.total_pii_redacted += result.pii_count

            if result.is_spam:
                metrics.total_spam_detected += 1
            if result.is_duplicate:
                metrics.total_duplicates += 1

            if result.passed and filtered_article is not None:
                kept.append(filtered_article)
                metrics.total_passed += 1
            else:
                metrics.total_rejected += 1
                layer = result.rejected_by or "unknown"
                metrics.rejections_by_layer[layer] = (
                    metrics.rejections_by_layer.get(layer, 0) + 1
                )
                logger.debug(
                    "FilteringPipeline: rejected id=%s by=%s reason=%s",
                    article.id,
                    result.rejected_by,
                    result.rejection_reason,
                )

        logger.info(
            "FilteringPipeline.filter_batch: in=%d kept=%d rejected=%d "
            "rate=%.1f%% spam=%d dup=%d pii_redacted=%d",
            metrics.total_input,
            metrics.total_passed,
            metrics.total_rejected,
            metrics.rejection_rate * 100,
            metrics.total_spam_detected,
            metrics.total_duplicates,
            metrics.total_pii_redacted,
        )
        return kept, metrics
