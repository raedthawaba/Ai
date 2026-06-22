from typing import List, Optional, Dict, Any
from ..metadata_store.sqlite_catalog import SQLiteCatalog, Pipeline

class PipelineRepository:
    """Repository for managing Pipeline entities in the metadata store."""

    def __init__(self, catalog: SQLiteCatalog):
        self.catalog = catalog
        self.table_name = "pipelines"

    async def create(self, pipeline_data: Dict[str, Any]) -> str:
        """Creates a new pipeline record."""
        return await self.catalog.insert_record(self.table_name, pipeline_data)

    async def get(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a pipeline by ID."""
        return await self.catalog.get_record(self.table_name, pipeline_id)

    async def list(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lists pipelines based on filters."""
        pipelines = []
        async for pipeline in self.catalog.search_records(self.table_name, filters=filters, limit=limit):
            pipelines.append(pipeline)
        return pipelines

    async def update(self, pipeline_id: str, updates: Dict[str, Any]) -> None:
        """Updates an existing pipeline record."""
        await self.catalog.update_record(self.table_name, pipeline_id, updates)

    async def delete(self, pipeline_id: str) -> None:
        """Deletes a pipeline record."""
        await self.catalog.delete_record(self.table_name, pipeline_id)
