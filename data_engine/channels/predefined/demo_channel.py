"""Demo channel implementation returning deterministic mock articles with storage integration."""

from __future__ import annotations

import json
from typing import Optional

from shared.schemas.article import Article, ArticleMetadata
from data_engine.channels.base import BaseChannel, FetchResult
from shared.utils.datetime_utils import utc_now
from data_engine.storage.storage_manager import StorageManager


class DemoChannel(BaseChannel):
    """Demo channel that returns static articles and stores them using StorageManager."""

    def __init__(self, config, storage_manager: Optional[StorageManager] = None):
        super().__init__(config)
        self.storage_manager = storage_manager or StorageManager()

    async def fetch(self, last_fetched_id: str | None = None) -> FetchResult:
        """Return a predefined set of mock articles."""
        published_at = utc_now()
        mock_articles = [
            Article(
                id="demo_art_001",
                title="مقال تجريبي أول: مستقبل الذكاء الاصطناعي",
                content="هذا محتوى تجريبي يتحدث عن تطور تقنيات الذكاء الاصطناعي في عام 2024 وما بعده.",
                url="https://example.com/demo1",
                published_at=published_at,
                metadata=ArticleMetadata(
                    source_id=self.config.id,
                    author="نظام هجين",
                    language="ar",
                    tags=["AI", "Future", "Demo"],
                ),
            ),
            Article(
                id="demo_art_002",
                title="Demo Article 2: Data Engineering Basics",
                content="This is a mock content about the fundamentals of building robust data pipelines.",
                url="https://example.com/demo2",
                published_at=published_at,
                metadata=ArticleMetadata(
                    source_id=self.config.id,
                    author="Hajeen System",
                    language="en",
                    tags=["Data", "Engineering", "Demo"],
                ),
            ),
        ]
        return FetchResult(
            articles=mock_articles,
            has_more=False,
            metadata={"source_type": "demo", "count": len(mock_articles)},
        )

    async def run_pipeline(self, articles: list[Article]) -> list[Article]:
        """
        Run a pipeline that stores raw data, bronze data, and metadata.
        """
        await self.storage_manager.connect()
        try:
            for article in articles:
                # 1. Store Raw Data
                raw_payload = {
                    "id": article.id,
                    "title": article.title,
                    "content": article.content,
                    "url": str(article.url),
                    "published_at": article.published_at.isoformat(),
                    "metadata": article.metadata.model_dump()
                }
                raw_key = await self.storage_manager.store_raw_response(
                    data=json.dumps(raw_payload, ensure_ascii=False),
                    key=f"api/{article.id}.json",
                    metadata={"source": self.config.id}
                )

                # 2. Store Bronze Data (Cleaned)
                bronze_data = {
                    "id": article.id,
                    "raw_data_key": raw_key,
                    "cleaned_content": article.content.strip(),
                    "metadata": {"source_id": self.config.id},
                    "timestamp": utc_now().isoformat()
                }
                bronze_key = await self.storage_manager.save_bronze_data(
                    data=bronze_data,
                    key=f"articles/{article.id}",
                    schema_name="BronzeSchema"
                )

                # 3. Register in Metadata Catalog (SQLite)
                article_record = {
                    "id": article.id,
                    "channel_id": self.config.id,
                    "title": article.title,
                    "raw_data_key": raw_key,
                    "bronze_data_key": bronze_key,
                    "published_at": article.published_at,
                    "metadata": article.metadata.model_dump(),
                    "is_active": True
                }
                await self.storage_manager.save_article(article_record)

            self.last_run = utc_now()
            self.total_fetched += len(articles)
            return articles
        finally:
            await self.storage_manager.disconnect()

    async def validate_source(self) -> bool:
        """Validate that the configured source type is demo."""
        return self.config.source.type == "demo"
