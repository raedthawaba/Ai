import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional, Union

from pydantic import BaseModel, ValidationError, Field

from ..base import BaseProcessedStorage

class BronzeSchema(BaseModel):
    id: str
    raw_data_key: str
    cleaned_content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BronzeLayer(BaseProcessedStorage):
    """Implementation of the Bronze layer for processed data storage.
    This layer stores data after initial cleaning.
    """

    def __init__(self, base_dir: Union[str, Path] = "./data/processed/bronze") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> None:
        """Ensures the base directory exists."""
        await asyncio.to_thread(self.base_dir.mkdir, parents=True, exist_ok=True)

    async def disconnect(self) -> None:
        """No explicit disconnection needed for local filesystem."""
        pass

    async def health_check(self) -> Dict[str, Any]:
        """Checks if the base directory is accessible and writable."""
        status = {"status": "ok", "path": str(self.base_dir)}
        try:
            if not await asyncio.to_thread(self.base_dir.is_dir):
                status["status"] = "error"
                status["message"] = "Base directory does not exist."
                return status
            test_file = self.base_dir / ".health_check_test"
            await asyncio.to_thread(test_file.write_text, "test")
            await asyncio.to_thread(test_file.unlink)
        except Exception as e:
            status["status"] = "error"
            status["message"] = f"Cannot access or write to base directory: {e}"
        return status

    def _get_storage_path(self, key: str, version: Optional[str] = None) -> Path:
        """Constructs the full path for a given key, organizing by date and type.
        Keys are expected to be in the format 'schema_name/item_id'.
        """
        parts = key.split("/")
        if len(parts) < 2:
            raise ValueError("Key must be in the format 'schema_name/item_id'")
        
        schema_name = parts[0]
        item_id = parts[1]

        today = datetime.now()
        date_path = self.base_dir / schema_name / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
        
        file_name = f"{item_id}.json"
        if version:
            file_name = f"{item_id}_v{version}.json"
            
        return date_path / file_name

    async def save_processed(self, data: Dict[str, Any], key: str, schema_name: str, version: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Saves processed data to the local filesystem with schema validation.

        Args:
            data (Dict[str, Any]): The processed data to save.
            key (str): A unique identifier for the data (e.g., 'bronze/article_123').
            schema_name (str): The name of the schema to use for validation (e.g., 'BronzeSchema').
            version (Optional[str]): Optional version of the data.
            metadata (Optional[Dict[str, Any]]): Optional metadata associated with the data.

        Returns:
            str: The relative path where the data was saved.

        Raises:
            ValidationError: If the data does not conform to the specified schema.
        """
        if schema_name == "BronzeSchema":
            validated_data = BronzeSchema(**data).model_dump_json(indent=2)
        else:
            raise ValueError(f"Unsupported schema: {schema_name}")

        file_path = self._get_storage_path(key, version)
        await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(file_path.write_text, validated_data, encoding="utf-8")
        return str(file_path.relative_to(self.base_dir))

    async def load_processed(self, key: str, schema_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Loads processed data from the local filesystem with schema validation.

        Args:
            key (str): The unique identifier of the data to load (relative path).
            schema_name (str): The name of the schema to use for validation.
            version (Optional[str]): Optional version of the data.

        Returns:
            Dict[str, Any]: The loaded and validated processed data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
            ValidationError: If the loaded data does not conform to the specified schema.
        """
        file_path = self.base_dir / key # Key is expected to be the relative path from save_processed
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"Processed data not found: {key}")
        
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        data = json.loads(content)

        if schema_name == "BronzeSchema":
            validated_data = BronzeSchema(**data).model_dump()
        else:
            raise ValueError(f"Unsupported schema: {schema_name}")
        
        return validated_data

    async def delete_processed(self, key: str, schema_name: str, version: Optional[str] = None) -> None:
        """Deletes processed data from the local filesystem.

        Args:
            key (str): The unique identifier of the data to delete (relative path).
            schema_name (str): The name of the schema (not used for deletion, but kept for interface consistency).
            version (Optional[str]): Optional version of the data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        file_path = self.base_dir / key
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"Processed data not found: {key}")
        await asyncio.to_thread(file_path.unlink)

    async def list_processed(self, schema_name: str, prefix: Optional[str] = None) -> AsyncIterator[str]:
        """Lists processed data keys in the local filesystem.

        Args:
            schema_name (str): The name of the schema to filter by (e.g., 'BronzeSchema').
            prefix (Optional[str]): An optional prefix to filter the listed keys.

        Returns:
            AsyncIterator[str]: An asynchronous iterator over the keys of the processed data.
        """
        search_path = self.base_dir
        if prefix:
            search_path = self.base_dir / prefix

        for file_path in await asyncio.to_thread(lambda: list(search_path.rglob("*.json"))):
            if await asyncio.to_thread(file_path.is_file):
                relative_path = str(file_path.relative_to(self.base_dir))
                yield relative_path
