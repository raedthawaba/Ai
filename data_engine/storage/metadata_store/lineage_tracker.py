from datetime import datetime
from typing import Any, Dict, Optional, AsyncIterator

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

Base = declarative_base()

class DataLineage(Base):
    __tablename__ = "data_lineage"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_key = Column(String, nullable=False, index=True)
    source_layer = Column(String, nullable=False)
    target_key = Column(String, nullable=False, index=True)
    target_layer = Column(String, nullable=False)
    transformation_type = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)
    metadata_ = Column(JSON, nullable=True, name='metadata')

class LineageTracker:
    """Tracks data lineage within the Hajeen AI Platform."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def record_lineage(self, 
                             source_key: str,
                             source_layer: str,
                             target_key: str,
                             target_layer: str,
                             transformation_type: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None) -> None:
        """Records a data transformation event."""
        async with self.session_factory() as session:
            lineage_entry = DataLineage(
                source_key=source_key,
                source_layer=source_layer,
                target_key=target_key,
                target_layer=target_layer,
                transformation_type=transformation_type,
                metadata_=metadata,
            )
            session.add(lineage_entry)
            await session.commit()

    async def get_lineage_for_key(self, key: str, layer: str) -> AsyncIterator[Dict[str, Any]]:
        """Retrieves lineage records for a given data key and layer."""
        async with self.session_factory() as session:
            stmt = select(DataLineage).where(
                (DataLineage.source_key == key) & (DataLineage.source_layer == layer) |
                (DataLineage.target_key == key) & (DataLineage.target_layer == layer)
            )
            result = await session.execute(stmt)
            for row in result.scalars():
                yield row.__dict__
