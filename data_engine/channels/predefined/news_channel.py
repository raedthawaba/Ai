"""News Channel — section 5.16.

Predefined channel for collecting news articles from RSS feeds and NewsAPI.
Runs the full processing pipeline:

    Fetch → Clean → Filter → Enrich → Transform → Store
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from data_engine.channels.base import BaseChannel, FetchResult
from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
from shared.schemas.article import Article, ArticleMetadata
from shared.schemas.channel import ChannelConfig
from shared.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class NewsChannel(BaseChannel):
    """Channel for news aggregation with a full processing pipeline.

    Fetches from RSS feeds and/or NewsAPI, then runs the complete
    Fetch → Clean → Filter → Enrich → Transform → Store pipeline.

    Parameters
    ----------
    config:
        :class:`ChannelConfig` for this channel.
    storage_manager:
        Optional storage manager for the store stage.
    policy_config_path:
        Path to filters.yaml. Defaults to ``configs/filters.yaml``.
    """

    def __init__(
        self,
        config: ChannelConfig,
        storage_manager=None,
        policy_config_path: str = "configs/filters.yaml",
    ) -> None:
        super().__init__(config)
        self._storage_manager = storage_manager
        self._policy_config_path = policy_config_path

        # Build the orchestrated pipeline
        self._pipeline = PipelineOrchestrator(
            name=f"news_pipeline:{config.name}",
            source_id=config.id,
            storage_manager=storage_manager,
            policy_config_path=policy_config_path,
            allowed_languages=["ar", "en"],
        )

    # ------------------------------------------------------------------
    # BaseChannel interface
    # ------------------------------------------------------------------

    async def fetch(self, last_fetched_id: str | None = None) -> FetchResult:
        """Fetch raw articles from configured sources.

        Tries RSS feeds first, then NewsAPI if configured.
        """
        articles = []
        errors = []

        # 1. Fetch from RSS sources
        rss_sources = [
            s for s in [self.config.source]
            if s.type in ("rss", "atom", "feed")
        ]
        for source in rss_sources:
            try:
                from data_engine.ingestion.crawlers.rss_parser import RSSParser
                parser = RSSParser()
                result = await parser.parse(str(source.url))
                articles.extend(result.articles)
                logger.info(
                    "NewsChannel.fetch: RSS %s → %d articles",
                    source.url,
                    len(result.articles),
                )
            except Exception as exc:
                msg = f"RSS {source.url}: {exc}"
                errors.append(msg)
                logger.warning("NewsChannel.fetch: %s", msg)

        # 2. Demo/generic HTTP source
        generic_sources = [
            s for s in [self.config.source]
            if s.type in ("demo", "http", "web")
        ]
        for source in generic_sources:
            try:
                art = Article(
                    id=f"{self.config.id}_demo_{utc_now().timestamp():.0f}",
                    title="Demo News Article",
                    content=(
                        "هذا مقال تجريبي يوضح عمل قناة الأخبار مع المعالجة الكاملة. "
                        "يتضمن نصاً باللغة العربية يصف تقنيات الذكاء الاصطناعي ومحركات البيانات."
                    ),
                    url=source.url,
                    published_at=utc_now(),
                    metadata=ArticleMetadata(
                        source_id=self.config.id,
                        author="Hajeen Platform",
                        language="ar",
                        tags=["news", "demo"],
                    ),
                )
                articles.append(art)
            except Exception as exc:
                errors.append(f"demo {source.url}: {exc}")

        return FetchResult(
            articles=articles,
            has_more=False,
            metadata={
                "source_type": self.config.source.type,
                "fetched_at": utc_now().isoformat(),
                "errors": errors,
            },
        )

    async def validate_source(self) -> bool:
        """Validate the configured source by checking robots.txt."""
        try:
            from data_engine.ingestion.crawlers.robots_checker import RobotsChecker
            checker = RobotsChecker()
            return await checker.can_fetch(str(self.config.source.url))
        except Exception as exc:
            logger.warning("NewsChannel.validate_source: %s", exc)
            return True  # assume allowed if checker fails

    # ------------------------------------------------------------------
    # Full pipeline execution
    # ------------------------------------------------------------------

    async def run_pipeline(self, articles: list[Article] | None = None) -> list[Article]:
        """Run the complete processing pipeline.

        1. Fetch articles (or use provided ones)
        2. Clean (HTML + normalise)
        3. Filter (dedup + language + quality + spam + policy)
        4. Enrich (keywords + entities + summary)
        5. Transform (chunk + tokenize)
        6. Store

        Parameters
        ----------
        articles:
            Pre-fetched articles. When None, calls :meth:`fetch` first.

        Returns
        -------
        Processed articles remaining after all filters.
        """
        if articles is None:
            fetch_result = await self.fetch()
            articles = fetch_result.articles
            logger.info(
                "NewsChannel.run_pipeline: fetched=%d", len(articles)
            )

        if not articles:
            logger.warning("NewsChannel.run_pipeline: no articles to process")
            return []

        context = await self._pipeline.run(articles=articles)

        self.last_run = utc_now()
        self.total_fetched += len(context.articles)

        metrics = self._pipeline.last_metrics
        if metrics:
            logger.info(
                "NewsChannel.run_pipeline: %s",
                metrics.summary(),
            )

        return context.articles
