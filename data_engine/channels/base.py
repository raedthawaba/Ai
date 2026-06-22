"""Base abstractions for channel implementations."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.article import Article
from shared.schemas.channel import ChannelConfig, ChannelStats, ChannelStatus
from shared.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class FetchResult(BaseModel):
    """Represents the result of a channel fetch operation."""

    model_config = ConfigDict(extra="forbid")

    articles: list[Article] = Field(default_factory=list, description="Fetched articles")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Fetch metadata")
    has_more: bool = Field(default=False, description="Whether more results are available")


class BaseChannel(ABC):
    """Abstract base class for all channel implementations."""

    def __init__(self, config: ChannelConfig) -> None:
        self.config = config
        self.last_run: Optional[datetime] = None
        self.total_fetched: int = 0

    @abstractmethod
    async def fetch(self, last_fetched_id: Optional[str] = None) -> FetchResult:
        """Fetch new data from the configured source."""

    @abstractmethod
    async def validate_source(self) -> bool:
        """Validate the configured data source."""

    async def run_pipeline(self, articles: list[Article]) -> list[Article]:
        """Run the full processing pipeline for the supplied articles.

        يستخدم PipelineOrchestrator الحقيقي لمعالجة البيانات.
        """
        from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
        from data_engine.storage.storage_manager import get_storage_manager

        self.last_run = utc_now()

        if not articles:
            logger.info("[%s] run_pipeline: لا توجد مقالات للمعالجة", self.config.id)
            return []

        try:
            storage = get_storage_manager()
            await storage.connect()
        except Exception as exc:
            logger.warning("[%s] run_pipeline: تعذّر تهيئة StorageManager — %s", self.config.id, exc)
            storage = None

        try:
            orchestrator = PipelineOrchestrator(
                name=f"channel:{self.config.name}",
                source_id=self.config.id,
                storage_manager=storage,
                allowed_languages=["ar", "en"],
            )

            context = await orchestrator.run(articles=articles)
            processed = context.articles

            self.total_fetched += len(articles)
            self._update_stats(
                fetched=len(articles),
                processed=len(processed),
                stored=context.get("stored_count", 0) or 0,
                success=True,
            )

            logger.info(
                "[%s] run_pipeline: في=%d خارج=%d",
                self.config.id,
                len(articles),
                len(processed),
            )
            return processed

        except Exception as exc:
            logger.error("[%s] run_pipeline: خطأ — %s", self.config.id, exc, exc_info=True)
            self._update_stats(
                fetched=len(articles),
                processed=0,
                stored=0,
                success=False,
                error=str(exc),
            )
            self.update_status(ChannelStatus.ERROR)
            return articles  # إعادة ما تم جلبه دون معالجة
        finally:
            if storage is not None:
                try:
                    await storage.disconnect()
                except Exception:
                    pass

    def _update_stats(
        self,
        fetched: int,
        processed: int,
        stored: int,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """تحديث إحصائيات القناة بعد كل تشغيل."""
        stats = self.config.stats
        stats.total_runs += 1
        stats.total_fetched += fetched
        stats.total_processed += processed
        stats.total_stored += stored
        stats.last_run_at = utc_now()

        if success:
            stats.successful_runs += 1
            stats.last_run_status = "success"
            stats.last_error = None
        else:
            stats.failed_runs += 1
            stats.last_run_status = "failed"
            if error:
                stats.last_error = error[:500]

    def get_status(self) -> ChannelStatus:
        """Return the channel status from the config."""
        return self.config.status

    def update_status(self, new_status: ChannelStatus) -> None:
        """Update the channel status and refresh the update timestamp."""
        self.config.status = new_status
        self.config.updated_at = utc_now()

    async def __aenter__(self) -> "BaseChannel":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None
