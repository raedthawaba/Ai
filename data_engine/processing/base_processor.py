"""Base Processor — section 5.1.

Abstract base class for all processing stages.  Provides:
- Async processing interface
- Automatic timing & result wrapping
- Error capture without crashing the pipeline
- Chainable processor composition
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from shared.schemas.article import Article
from .processing_context import ProcessingContext
from .processing_result import ProcessingResult

logger = logging.getLogger(__name__)


class BaseProcessor(ABC):
    """Abstract base for every processing stage.

    Subclasses implement :meth:`process_articles` which receives a list of
    articles and returns a (possibly shorter) list.  The base class handles
    timing, error capture, and context updates automatically.

    Parameters
    ----------
    name:
        Human-readable processor identifier used in logs and metrics.
    enabled:
        When ``False`` the processor is a no-op (articles pass through
        unchanged).
    """

    def __init__(self, name: str, enabled: bool = True) -> None:
        self.name = name
        self.enabled = enabled
        self._call_count = 0
        self._total_processed = 0
        self._total_rejected = 0

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        """Transform or filter *articles*.

        Parameters
        ----------
        articles:
            Input articles for this stage.
        context:
            Shared pipeline context (read config, write metadata).

        Returns
        -------
        Processed / filtered article list.
        """

    # ------------------------------------------------------------------
    # Public execution entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        context: ProcessingContext,
    ) -> ProcessingResult:
        """Execute the processor against ``context.articles``.

        Wraps :meth:`process_articles`, measures wall-clock duration,
        captures non-fatal exceptions, records the result in the context,
        and replaces ``context.articles`` with the output.

        Parameters
        ----------
        context:
            Shared pipeline context.

        Returns
        -------
        :class:`ProcessingResult` for this stage.
        """
        if context.is_aborted:
            logger.debug("%s: skipped (pipeline aborted)", self.name)
            return ProcessingResult.empty(self.name)

        if not self.enabled:
            logger.debug("%s: skipped (disabled)", self.name)
            result = ProcessingResult.from_articles(
                stage_name=self.name,
                input_count=context.article_count,
                output_articles=context.articles,
            )
            context.record_stage(result)
            return result

        input_articles = list(context.articles)
        input_count = len(input_articles)
        start = time.monotonic()

        try:
            output_articles = await self.process_articles(input_articles, context)
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error(
                "%s: fatal error after %.1fms — %s", self.name, duration_ms, exc
            )
            result = ProcessingResult(
                stage_name=self.name,
                input_count=input_count,
                output_articles=input_articles,
                duration_ms=duration_ms,
            )
            result.add_error(self.name, str(exc), exc=exc)
            context.record_stage(result)
            return result

        duration_ms = (time.monotonic() - start) * 1000
        rejected = max(0, input_count - len(output_articles))

        self._call_count += 1
        self._total_processed += len(output_articles)
        self._total_rejected += rejected

        result = ProcessingResult.from_articles(
            stage_name=self.name,
            input_count=input_count,
            output_articles=output_articles,
            duration_ms=duration_ms,
        )

        context.replace_articles(output_articles)
        context.record_stage(result)

        logger.info(
            "%s: in=%d out=%d rejected=%d (%.1fms)",
            self.name,
            input_count,
            len(output_articles),
            rejected,
            duration_ms,
        )
        return result

    # ------------------------------------------------------------------
    # Chaining
    # ------------------------------------------------------------------

    def chain(self, other: "BaseProcessor") -> "ChainedProcessor":
        """Return a new processor that runs ``self`` then ``other``.

        Parameters
        ----------
        other:
            The next processor in the chain.

        Returns
        -------
        A :class:`ChainedProcessor` combining both.

        Example
        -------
        .. code-block:: python

            pipeline = cleaner.chain(filter_).chain(enricher)
            await pipeline.run(context)
        """
        return ChainedProcessor(self, other)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """Return lifetime processing statistics."""
        return {
            "name": self.name,
            "calls": self._call_count,
            "total_processed": self._total_processed,
            "total_rejected": self._total_rejected,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, enabled={self.enabled})"


class ChainedProcessor(BaseProcessor):
    """Executes two processors sequentially.

    Created automatically by :meth:`BaseProcessor.chain`.
    """

    def __init__(self, first: BaseProcessor, second: BaseProcessor) -> None:
        super().__init__(name=f"{first.name}→{second.name}")
        self._first = first
        self._second = second

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        context.replace_articles(articles)
        await self._first.run(context)
        await self._second.run(context)
        return context.articles

    async def run(self, context: ProcessingContext) -> ProcessingResult:
        await self._first.run(context)
        await self._second.run(context)
        return ProcessingResult.from_articles(
            stage_name=self.name,
            input_count=context.article_count,
            output_articles=context.articles,
        )


class PassthroughProcessor(BaseProcessor):
    """A no-op processor that passes articles unchanged (useful for testing)."""

    def __init__(self, name: str = "passthrough") -> None:
        super().__init__(name=name)

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        return articles
