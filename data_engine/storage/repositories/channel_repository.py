from typing import List, Optional, Dict, Any
from ..metadata_store.sqlite_catalog import SQLiteCatalog, Channel

class ChannelRepository:
    """Repository for managing Channel entities in the metadata store."""

    def __init__(self, catalog: SQLiteCatalog):
        self.catalog = catalog
        self.table_name = "channels"

    async def create(self, channel_data: Dict[str, Any]) -> str:
        """Creates a new channel record."""
        return await self.catalog.insert_record(self.table_name, channel_data)

    async def get(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a channel by ID."""
        return await self.catalog.get_record(self.table_name, channel_id)

    async def list(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lists channels based on filters."""
        channels = []
        async for channel in self.catalog.search_records(self.table_name, filters=filters, limit=limit):
            channels.append(channel)
        return channels

    async def update(self, channel_id: str, updates: Dict[str, Any]) -> None:
        """Updates an existing channel record."""
        await self.catalog.update_record(self.table_name, channel_id, updates)

    async def delete(self, channel_id: str) -> None:
        """Deletes a channel record."""
        await self.catalog.delete_record(self.table_name, channel_id)
