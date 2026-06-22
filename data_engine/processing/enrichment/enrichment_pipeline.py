"""Enrichment Pipeline — Phase 2 (Section 2.4).

Pipeline إثراء موحّد يجمع:
  1. ContentEnricher   — ملخص + كلمات مفتاحية + كيانات تاريخية
  2. KeywordExtractor  — YAKE أو frequency-based
  3. EntityExtractor   — spaCy أو regex fallback
  4. Summarizer        — extractive summary
  5. TopicClassifier   — تصنيف موضوعي
  6. SentimentAnalyzer — تحليل مشاعر

المزايا:
  - lazy loading للنماذج (لا تُحمَّل عند startup)
  - enrichment caching (تجنّب إعادة المعالجة)
  - async-safe via asyncio.to_thread
  - batching مُحسَّن
  - EnrichmentMetrics شاملة
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article
from .content_enricher import ContentEnricher, EnricherConfig
from .keyword_extractor import KeywordExtractor, KeywordExtractorConfig
from .entity_extractor import EntityExtractor, EntityExtractorConfig
from .summarizer import Summarizer, SummarizerConfig
from .topic_classifier import TopicClassifier, TopicClassifierConfig
from .sentiment_analyzer import SentimentAnalyzer, SentimentConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EnrichmentPipelineConfig:
    """إعدادات Enrichment Pipeline الموحّد."""

    # تفعيل / تعطيل كل مرحلة
    use_content_enricher: bool = True
    use_keyword_extractor: bool = True
    use_entity_extractor: bool = True
    use_summarizer: bool = True
    use_topic_classifier: bool = True
    use_sentiment_analyzer: bool = True

    # Caching
    enable_cache: bool = True
    cache_max_size: int = 1000    # عدد أقصى للمقالات في الـ cache

    # إعدادات كل مرحلة
    enricher_config: Optional[EnricherConfig] = None
    keyword_config: Optional[KeywordExtractorConfig] = None
    entity_config: Optional[EntityExtractorConfig] = None
    summarizer_config: Optional[SummarizerConfig] = None
    topic_config: Optional[TopicClassifierConfig] = None
    sentiment_config: Optional[SentimentConfig] = None

    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment Metrics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArticleEnrichmentMetrics:
    """مقاييس إثراء مقال واحد."""
    article_id: str
    keywords_added: int = 0
    entities_added: int = 0
    has_summary: bool = False
    has_topic: bool = False
    has_sentiment: bool = False
    from_cache: bool = False
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class EnrichmentMetrics:
    """مقاييس إثراء دُفعة كاملة."""
    total_input: int = 0
    total_enriched: int = 0
    total_from_cache: int = 0
    total_errors: int = 0
    total_duration_ms: float = 0.0
    article_metrics: List[ArticleEnrichmentMetrics] = field(default_factory=list)

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total_input if self.total_input else 0.0

    @property
    def cache_hit_rate(self) -> float:
        return self.total_from_cache / self.total_input if self.total_input else 0.0

    def to_dict(self) -> dict:
        return {
            "total_input": self.total_input,
            "total_enriched": self.total_enriched,
            "total_from_cache": self.total_from_cache,
            "total_errors": self.total_errors,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "cache_hit_rate": round(self.cache_hit_rate, 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Simple LRU Cache
# ─────────────────────────────────────────────────────────────────────────────

def _article_cache_key(article: Article) -> str:
    """مفتاح cache فريد للمقال."""
    raw = f"{article.id}::{article.content[:200]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class _EnrichmentCache:
    """Cache بسيط بحجم أقصى (LRU)."""

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: Dict[str, Article] = {}
        self._order: List[str] = []
        self._max_size = max_size

    def get(self, key: str) -> Optional[Article]:
        return self._cache.get(key)

    def set(self, key: str, article: Article) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self._max_size:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = article
        self._order.append(key)

    def clear(self) -> None:
        self._cache.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._cache)


# ─────────────────────────────────────────────────────────────────────────────
# EnrichmentPipeline
# ─────────────────────────────────────────────────────────────────────────────

class EnrichmentPipeline:
    """Pipeline إثراء موحّد مع lazy loading وcaching.

    المعالجات تُحمَّل عند أول استخدام لتجنّب استهلاك الذاكرة عند startup.

    Parameters
    ----------
    config:
        EnrichmentPipelineConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[EnrichmentPipelineConfig] = None) -> None:
        self.config = config or EnrichmentPipelineConfig()
        self._cache = _EnrichmentCache(max_size=self.config.cache_max_size) if self.config.enable_cache else None

        # Lazy-loaded processors
        self._content_enricher: Optional[ContentEnricher] = None
        self._keyword_extractor: Optional[KeywordExtractor] = None
        self._entity_extractor: Optional[EntityExtractor] = None
        self._summarizer: Optional[Summarizer] = None
        self._topic_classifier: Optional[TopicClassifier] = None
        self._sentiment_analyzer: Optional[SentimentAnalyzer] = None

    # ─── Lazy getters ──────────────────────────────────────────────────────

    @property
    def content_enricher(self) -> ContentEnricher:
        if self._content_enricher is None:
            self._content_enricher = ContentEnricher(self.config.enricher_config)
        return self._content_enricher

    @property
    def keyword_extractor(self) -> KeywordExtractor:
        if self._keyword_extractor is None:
            self._keyword_extractor = KeywordExtractor(self.config.keyword_config)
        return self._keyword_extractor

    @property
    def entity_extractor(self) -> EntityExtractor:
        if self._entity_extractor is None:
            self._entity_extractor = EntityExtractor(self.config.entity_config)
        return self._entity_extractor

    @property
    def summarizer(self) -> Summarizer:
        if self._summarizer is None:
            self._summarizer = Summarizer(self.config.summarizer_config)
        return self._summarizer

    @property
    def topic_classifier(self) -> TopicClassifier:
        if self._topic_classifier is None:
            self._topic_classifier = TopicClassifier(self.config.topic_config)
        return self._topic_classifier

    @property
    def sentiment_analyzer(self) -> SentimentAnalyzer:
        if self._sentiment_analyzer is None:
            self._sentiment_analyzer = SentimentAnalyzer(self.config.sentiment_config)
        return self._sentiment_analyzer

    # ─── Single article enrichment ────────────────────────────────────────

    def enrich_article(
        self, article: Article
    ) -> Tuple[Article, ArticleEnrichmentMetrics]:
        """إثراء مقال واحد.

        Parameters
        ----------
        article:
            المقال المصدر.

        Returns
        -------
        (enriched_article, metrics)
        """
        start = time.monotonic()
        metrics = ArticleEnrichmentMetrics(article_id=article.id)

        # فحص الـ cache
        if self._cache is not None:
            cache_key = _article_cache_key(article)
            cached = self._cache.get(cache_key)
            if cached is not None:
                metrics.from_cache = True
                metrics.duration_ms = (time.monotonic() - start) * 1000
                logger.debug("EnrichmentPipeline: cache hit id=%s", article.id)
                return cached, metrics

        cfg = self.config
        enriched = article

        try:
            # 1. ContentEnricher (summary + basic keywords + date entities)
            if cfg.use_content_enricher:
                enriched = self.content_enricher.enrich_article(enriched)

            # 2. KeywordExtractor (YAKE أو frequency)
            if cfg.use_keyword_extractor:
                before_tags = len(enriched.metadata.tags)
                enriched = self.keyword_extractor.enrich_article(enriched)
                metrics.keywords_added = len(enriched.metadata.tags) - before_tags

            # 3. EntityExtractor (spaCy أو regex)
            if cfg.use_entity_extractor:
                before_entities = len(enriched.metadata.entities)
                enriched = self.entity_extractor.enrich_article(enriched)
                metrics.entities_added = len(enriched.metadata.entities) - before_entities

            # 4. Summarizer
            if cfg.use_summarizer:
                enriched = self.summarizer.summarize_article(enriched)
                metrics.has_summary = bool(enriched.summary)

            # 5. TopicClassifier
            if cfg.use_topic_classifier:
                enriched = self.topic_classifier.enrich_article(enriched)
                metrics.has_topic = "primary_topic" in enriched.metadata.extra

            # 6. SentimentAnalyzer
            if cfg.use_sentiment_analyzer:
                enriched = self.sentiment_analyzer.enrich_article(enriched)
                metrics.has_sentiment = "sentiment" in enriched.metadata.extra

            # حفظ في الـ cache
            if self._cache is not None:
                self._cache.set(cache_key, enriched)

        except Exception as exc:
            logger.error(
                "EnrichmentPipeline: خطأ في إثراء id=%s — %s",
                article.id, exc,
            )
            metrics.error = str(exc)
            enriched = article  # استرجاع المقال الأصلي

        metrics.duration_ms = (time.monotonic() - start) * 1000
        return enriched, metrics

    # ─── Batch enrichment ──────────────────────────────────────────────────

    def enrich_batch(
        self, articles: List[Article]
    ) -> Tuple[List[Article], EnrichmentMetrics]:
        """إثراء دُفعة من المقالات.

        Parameters
        ----------
        articles:
            قائمة المقالات.

        Returns
        -------
        (enriched_articles, metrics)
        """
        batch_metrics = EnrichmentMetrics(total_input=len(articles))
        enriched_articles: List[Article] = []

        for article in articles:
            enriched, art_metrics = self.enrich_article(article)
            batch_metrics.article_metrics.append(art_metrics)
            batch_metrics.total_duration_ms += art_metrics.duration_ms
            enriched_articles.append(enriched)

            if art_metrics.from_cache:
                batch_metrics.total_from_cache += 1
            if art_metrics.error:
                batch_metrics.total_errors += 1
            else:
                batch_metrics.total_enriched += 1

        logger.info(
            "EnrichmentPipeline.enrich_batch: in=%d enriched=%d "
            "cache_hits=%d errors=%d avg_time=%.1fms",
            batch_metrics.total_input,
            batch_metrics.total_enriched,
            batch_metrics.total_from_cache,
            batch_metrics.total_errors,
            batch_metrics.avg_duration_ms,
        )
        return enriched_articles, batch_metrics

    # ─── Async API ─────────────────────────────────────────────────────────

    async def async_enrich_article(
        self, article: Article
    ) -> Tuple[Article, ArticleEnrichmentMetrics]:
        """إثراء مقال واحد بشكل async."""
        return await asyncio.to_thread(self.enrich_article, article)

    async def async_enrich_batch(
        self, articles: List[Article], max_concurrency: int = 5
    ) -> Tuple[List[Article], EnrichmentMetrics]:
        """إثراء دُفعة من المقالات بالتوازي."""
        sem = asyncio.Semaphore(max_concurrency)

        async def _enrich_one(a: Article) -> Tuple[Article, ArticleEnrichmentMetrics]:
            async with sem:
                return await self.async_enrich_article(a)

        results = await asyncio.gather(*[_enrich_one(a) for a in articles])

        batch_metrics = EnrichmentMetrics(total_input=len(articles))
        enriched_articles: List[Article] = []

        for enriched, art_metrics in results:
            batch_metrics.article_metrics.append(art_metrics)
            batch_metrics.total_duration_ms += art_metrics.duration_ms
            enriched_articles.append(enriched)
            if art_metrics.from_cache:
                batch_metrics.total_from_cache += 1
            if art_metrics.error:
                batch_metrics.total_errors += 1
            else:
                batch_metrics.total_enriched += 1

        return enriched_articles, batch_metrics

    def clear_cache(self) -> None:
        """إفراغ الـ cache."""
        if self._cache:
            self._cache.clear()
            logger.info("EnrichmentPipeline: cache cleared")

    @property
    def cache_size(self) -> int:
        """عدد المقالات في الـ cache."""
        return len(self._cache) if self._cache else 0
