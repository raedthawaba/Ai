"""Fetch Stage — section 5.14.

Receives articles from an external source and places them into the context.
When the context already has articles (injected externally), this stage
is a no-op so the pipeline can be used with pre-fetched data.
"""
from __future__ import annotations
import logging
from typing import List, Optional, Callable, Awaitable
from shared.schemas.article import Article
from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext

logger = logging.getLogger(__name__)


class FetchStage(BaseProcessor):
    """Pipeline stage that injects externally fetched articles.

    Parameters
    ----------
    fetch_fn:
        Optional async callable that returns a list of articles.
        When provided, it is called and results replace context articles.
        When omitted, the stage is a pass-through (articles already in context).
    name:
        Stage name for logging.
    """

    def __init__(
        self,
        fetch_fn: Optional[Callable[[], Awaitable[List[Article]]]] = None,
        name: str = "fetch",
    ) -> None:
        super().__init__(name=name)
        self._fetch_fn = fetch_fn

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        if self._fetch_fn is not None:
            try:
                fetched = await self._fetch_fn()
                context.set("fetch_count", len(fetched))
                logger.info("%s: fetched %d articles", self.name, len(fetched))
                return fetched
            except Exception as exc:
                logger.error("%s: fetch failed — %s", self.name, exc)
                context.record_error(self.name, str(exc))
                return articles  # return what we have

        # Pass-through: articles already loaded by caller
        context.set("fetch_count", len(articles))
        logger.info("%s: pass-through %d articles", self.name, len(articles))
        return articles
