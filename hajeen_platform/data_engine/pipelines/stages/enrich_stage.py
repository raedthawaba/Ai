"""Enrich Stage — section 5.14.

Applies keyword extraction, entity extraction, and summarisation.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from shared.schemas.article import Article
from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext
from data_engine.processing.enrichment.content_enricher import ContentEnricher, EnricherConfig
from data_engine.processing.enrichment.keyword_extractor import KeywordExtractor, KeywordExtractorConfig
from data_engine.processing.enrichment.entity_extractor import EntityExtractor, EntityExtractorConfig
from data_engine.processing.enrichment.summarizer import Summarizer, SummarizerConfig

logger = logging.getLogger(__name__)


class EnrichStage(BaseProcessor):
    """Enriches articles with keywords, entities, and summaries.

    Parameters
    ----------
    enricher_config / kw_config / entity_config / summarizer_config:
        Optional per-component config objects.
    name:
        Stage name.
    """

    def __init__(
        self,
        enricher_config: Optional[EnricherConfig] = None,
        kw_config: Optional[KeywordExtractorConfig] = None,
        entity_config: Optional[EntityExtractorConfig] = None,
        summarizer_config: Optional[SummarizerConfig] = None,
        name: str = "enrich",
    ) -> None:
        super().__init__(name=name)
        self._enricher = ContentEnricher(config=enricher_config)
        self._keywords = KeywordExtractor(config=kw_config)
        self._entities = EntityExtractor(config=entity_config)
        self._summarizer = Summarizer(config=summarizer_config)

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        # Base enrichment (reading time, tags, date hints)
        enriched = self._enricher.enrich_batch(articles)

        # Keyword extraction
        enriched = self._keywords.enrich_batch(enriched)

        # Entity extraction
        enriched = self._entities.enrich_batch(enriched)

        # Summarisation
        enriched = self._summarizer.summarize_batch(enriched)

        context.set("enriched_count", len(enriched))
        logger.info("%s: enriched %d articles", self.name, len(enriched))
        return enriched
