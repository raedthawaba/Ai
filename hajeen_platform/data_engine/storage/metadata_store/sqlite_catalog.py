import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncIterator, Union

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Boolean
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.future import select

from ..base import BaseMetadataStore

Base = declarative_base()

class Channel(Base):
    __tablename__ = "channels"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Article(Base):
    __tablename__ = "articles"
    id = Column(String, primary_key=True, index=True)
    channel_id = Column(String, nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(String, unique=True, nullable=True)
    raw_data_key = Column(String, nullable=False)
    bronze_data_key = Column(String, nullable=True)
    silver_data_key = Column(String, nullable=True)
    gold_data_key = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    ingested_at = Column(DateTime, default=datetime.now)
    metadata_ = Column(JSON, nullable=True, name='metadata') # Renamed to avoid conflict with Python keyword
    is_active = Column(Boolean, default=True)
    archived_at = Column(DateTime, nullable=True)

class Pipeline(Base):
    __tablename__ = "pipelines"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class IngestionLog(Base):
    __tablename__ = "ingestion_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, nullable=False, index=True)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, nullable=False) # e.g., 'success', 'failed', 'running'
    message = Column(Text, nullable=True)
    articles_ingested = Column(Integer, default=0)
    errors = Column(JSON, nullable=True)

class SQLiteCatalog(BaseMetadataStore):
    """SQLite implementation for the metadata catalog using SQLAlchemy 2.0."""

    def __init__(self, db_path: Union[str, Path] = "./data/metadata.db") -> None:
        self.db_path = Path(db_path).resolve()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", echo=False)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def connect(self) -> None:
        """Ensures the database file exists and tables are created."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def disconnect(self) -> None:
        """Closes the database connection."""
        await self.engine.dispose()

    async def health_check(self) -> Dict[str, Any]:
        """Performs a health check on the SQLite database."""
        status = {"status": "ok", "db_path": str(self.db_path)}
        try:
            async with self.SessionLocal() as session:
                await session.execute(select(Channel).limit(1))
        except Exception as e:
            status["status"] = "error"
            status["message"] = f"Database health check failed: {e}"
        return status

    async def create_table(self, table_name: str, schema: Dict[str, Any]) -> None:
        """Tables are created automatically on connect via Base.metadata.create_all.
        This method can be used for dynamic table creation if needed, but for now, it's a placeholder.
        """
        print(f"Table creation for {table_name} is handled by SQLAlchemy Base.metadata.create_all on connect.")

    async def insert_record(self, table_name: str, record: Dict[str, Any]) -> Any:
        """Inserts a record into a table."""
        async with self.SessionLocal() as session:
            model = self._get_model_by_table_name(table_name)
            instance = model(**record)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance.id if hasattr(instance, 'id') else None

    async def update_record(self, table_name: str, record_id: Any, updates: Dict[str, Any]) -> None:
        """Updates a record in a table."""
        async with self.SessionLocal() as session:
            model = self._get_model_by_table_name(table_name)
            stmt = select(model).where(model.id == record_id)
            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()
            if not instance:
                raise RecordNotFoundError(f"Record with ID {record_id} not found in {table_name}")
            for key, value in updates.items():
                setattr(instance, key, value)
            await session.commit()

    async def get_record(self, table_name: str, record_id: Any) -> Optional[Dict[str, Any]]:
        """Retrieves a record from a table."""
        async with self.SessionLocal() as session:
            model = self._get_model_by_table_name(table_name)
            stmt = select(model).where(model.id == record_id)
            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()
            if not instance:
                return None
            
            # Convert SQLAlchemy model to dict, excluding internal state
            data = {c.name: getattr(instance, c.name) for c in instance.__table__.columns}
            return data

    async def search_records(self, table_name: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> AsyncIterator[Dict[str, Any]]:
        """Searches for records in a table based on filters."""
        async with self.SessionLocal() as session:
            model = self._get_model_by_table_name(table_name)
            stmt = select(model)
            if filters:
                for key, value in filters.items():
                    stmt = stmt.where(getattr(model, key) == value)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            for row in result.scalars():
                data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
                yield data

    async def delete_record(self, table_name: str, record_id: Any) -> None:
        """Deletes a record from a table."""
        async with self.SessionLocal() as session:
            model = self._get_model_by_table_name(table_name)
            stmt = select(model).where(model.id == record_id)
            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()
            if not instance:
                raise RecordNotFoundError(f"Record with ID {record_id} not found in {table_name}")
            await session.delete(instance)
            await session.commit()

    def _get_model_by_table_name(self, table_name: str):
        """Helper to get the SQLAlchemy model class based on table name."""
        if table_name == "channels":
            return Channel
        elif table_name == "articles":
            return Article
        elif table_name == "pipelines":
            return Pipeline
        elif table_name == "ingestion_logs":
            return IngestionLog
        else:
            raise ValueError(f"Unknown table name: {table_name}")

class RecordNotFoundError(Exception):
    """Custom exception for when a record is not found."""
    pass
