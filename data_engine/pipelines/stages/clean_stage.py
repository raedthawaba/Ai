"""Clean Stage — section 5.14.

Applies HTML cleaning and text normalisation to all articles.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from shared.schemas.article import Article
from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext
from data_engine.processing.cleaning.html_cleaner import HTMLCleaner
from data_engine.processing.cleaning.text_normalizer import TextNormalizer, NormalizerConfig

logger = logging.getLogger(__name__)


class CleanStage(BaseProcessor):
    """Cleans article HTML and normalises text.

    Parameters
    ----------
    use_trafilatura:
        Pass to :class:`HTMLCleaner`.
    normalizer_config:
        Optional :class:`NormalizerConfig`.
    name:
        Stage name.
    """

    def __init__(
        self,
        use_trafilatura: bool = True,
        normalizer_config: Optional[NormalizerConfig] = None,
        name: str = "clean",
    ) -> None:
        super().__init__(name=name)
        self._html_cleaner = HTMLCleaner(use_trafilatura=use_trafilatura)
        self._normalizer = TextNormalizer(config=normalizer_config)

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        cleaned = self._html_cleaner.clean_batch(articles)
        normalised = self._normalizer.normalize_batch(cleaned)
        context.set("clean_count", len(normalised))
        logger.info("%s: cleaned %d articles", self.name, len(normalised))
        return normalised
