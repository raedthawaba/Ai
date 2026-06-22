"""Store Stage — section 5.14.

Persists processed articles using the available storage layers.
Falls back to local filesystem storage when the full storage manager is not
initialised (e.g. in test runs).
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import List, Optional
from shared.schemas.article import Article
from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path("./data/processed/pipeline")


class StoreStage(BaseProcessor):
    """Stores articles to the silver layer or local filesystem.

    Parameters
    ----------
    storage_manager:
        Optional StorageManager.  When provided, articles are saved via
        ``save_bronze_data`` + ``save_article``.  When None, articles are
        written as JSON files to *local_path*.
    local_path:
        Directory for local JSON storage (used when storage_manager is None).
    name:
        Stage name.
    """

    def __init__(
        self,
        storage_manager=None,
        local_path: Optional[Path] = None,
        name: str = "store",
    ) -> None:
        super().__init__(name=name)
        self._storage_manager = storage_manager
        self._local_path = local_path or _DEFAULT_STORE_PATH

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        if self._storage_manager is not None:
            stored = await self._store_via_manager(articles)
        else:
            stored = await self._store_local(articles)

        context.set("stored_count", stored)
        logger.info("%s: stored %d / %d articles", self.name, stored, len(articles))
        return articles  # pass-through; storage is a side-effect

    # ------------------------------------------------------------------
    async def _store_via_manager(self, articles: List[Article]) -> int:
        count = 0
        try:
            await self._storage_manager.connect()
            for article in articles:
                raw_payload = {
                    "id": article.id,
                    "title": article.title,
                    "content": article.content,
                    "url": str(article.url),
                    "published_at": article.published_at.isoformat(),
                    "summary": article.summary,
                    "metadata": article.metadata.model_dump(),
                }
                raw_key = await self._storage_manager.store_raw_response(
                    data=json.dumps(raw_payload, ensure_ascii=False),
                    key=f"articles/{article.id}.json",
                    metadata={"source": article.metadata.source_id},
                )
                bronze_data = {
                    "id": article.id,
                    "raw_data_key": raw_key,
                    "cleaned_content": article.content.strip(),
                    "metadata": {"source_id": article.metadata.source_id},
                }
                await self._storage_manager.save_bronze_data(
                    data=bronze_data,
                    key=f"articles/{article.id}",
                    schema_name="BronzeSchema",
                )
                count += 1
        except Exception as exc:
            logger.error("%s: storage_manager error — %s", self.name, exc)
        finally:
            try:
                await self._storage_manager.disconnect()
            except Exception:
                pass
        return count

    async def _store_local(self, articles: List[Article]) -> int:
        import asyncio
        count = 0

        def _write(article: Article) -> None:
            self._local_path.mkdir(parents=True, exist_ok=True)
            out_file = self._local_path / f"{article.id}.json"
            payload = {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "url": str(article.url),
                "published_at": article.published_at.isoformat(),
                "summary": article.summary,
                "metadata": article.metadata.model_dump(),
            }
            out_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        for article in articles:
            try:
                await asyncio.to_thread(_write, article)
                count += 1
            except Exception as exc:
                logger.error(
                    "%s: failed to store id=%s — %s", self.name, article.id, exc
                )
        return count
