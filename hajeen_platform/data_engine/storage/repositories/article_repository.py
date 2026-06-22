from typing import List, Optional, Dict, Any
from ..metadata_store.sqlite_catalog import SQLiteCatalog, Article

class ArticleRepository:
    """Repository for managing Article entities in the metadata store."""

    def __init__(self, catalog: SQLiteCatalog):
        self.catalog = catalog
        self.table_name = "articles"

    async def create(self, article_data: Dict[str, Any]) -> str:
        """Creates a new article record."""
        return await self.catalog.insert_record(self.table_name, article_data)

    async def get(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an article by ID."""
        return await self.catalog.get_record(self.table_name, article_id)

    async def list(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lists articles based on filters."""
        articles = []
        async for article in self.catalog.search_records(self.table_name, filters=filters, limit=limit):
            articles.append(article)
        return articles

    async def update(self, article_id: str, updates: Dict[str, Any]) -> None:
        """Updates an existing article record."""
        await self.catalog.update_record(self.table_name, article_id, updates)

    async def delete(self, article_id: str) -> None:
        """Deletes an article record."""
        await self.catalog.delete_record(self.table_name, article_id)
