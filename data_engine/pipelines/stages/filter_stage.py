"""Filter Stage — section 5.14.

Applies deduplication, language filtering, quality scoring, spam detection,
and policy filtering to the article batch.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from shared.schemas.article import Article
from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext
from data_engine.processing.filtering.deduplicator import Deduplicator, DeduplicatorConfig
from data_engine.processing.filtering.language_filter import LanguageFilter, LanguageFilterConfig
from data_engine.processing.filtering.quality_scorer import QualityScorer, QualityScorerConfig
from data_engine.processing.filtering.spam_detector import SpamDetector, SpamDetectorConfig
from data_engine.processing.filtering.policy_filter import PolicyFilter, PolicyFilterConfig

logger = logging.getLogger(__name__)


class FilterStage(BaseProcessor):
    """Full filtering pipeline: dedup → language → quality → spam → policy.

    Parameters
    ----------
    dedup_config / lang_config / quality_config / spam_config / policy_config:
        Optional per-filter config objects.
    allowed_languages:
        Shortcut to set allowed languages on the language filter.
    policy_config_path:
        Path to filters.yaml for the policy filter.
    name:
        Stage name.
    """

    def __init__(
        self,
        dedup_config: Optional[DeduplicatorConfig] = None,
        lang_config: Optional[LanguageFilterConfig] = None,
        quality_config: Optional[QualityScorerConfig] = None,
        spam_config: Optional[SpamDetectorConfig] = None,
        policy_config: Optional[PolicyFilterConfig] = None,
        allowed_languages: Optional[List[str]] = None,
        policy_config_path: Optional[str] = None,
        name: str = "filter",
    ) -> None:
        super().__init__(name=name)
        self._dedup = Deduplicator(config=dedup_config)

        lc = lang_config or LanguageFilterConfig()
        if allowed_languages:
            lc.allowed_languages = allowed_languages
        self._lang = LanguageFilter(config=lc)

        self._quality = QualityScorer(config=quality_config)
        self._spam = SpamDetector(config=spam_config)

        if policy_config is not None:
            self._policy = PolicyFilter(config=policy_config)
        else:
            self._policy = PolicyFilter(config_path=policy_config_path)

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        # 1. Deduplication
        dedup_result = self._dedup.deduplicate(articles)
        after_dedup = dedup_result.unique_articles
        context.set("dedup_removed", dedup_result.duplicate_count)

        # 2. Language filter
        lang_result = self._lang.filter_batch(after_dedup)
        after_lang = lang_result.kept
        context.set("lang_rejected", len(lang_result.rejected))

        # 3. Quality scoring
        after_quality, quality_scores = self._quality.filter_batch(after_lang)
        context.set("quality_rejected", len(after_lang) - len(after_quality))

        # 4. Spam detection
        after_spam, _ = self._spam.filter_batch(after_quality)
        context.set("spam_rejected", len(after_quality) - len(after_spam))

        # 5. Policy filter
        after_policy, _ = self._policy.filter_batch(after_spam)
        context.set("policy_rejected", len(after_spam) - len(after_policy))

        logger.info(
            "%s: in=%d dedup=%d lang=%d quality=%d spam=%d policy=%d out=%d",
            self.name,
            len(articles),
            dedup_result.duplicate_count,
            len(lang_result.rejected),
            len(after_lang) - len(after_quality),
            len(after_quality) - len(after_spam),
            len(after_spam) - len(after_policy),
            len(after_policy),
        )
        return after_policy
