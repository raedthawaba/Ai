import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional, Union

from ..base import BaseRawStorage

class LocalRawStorage(BaseRawStorage):
    """Local filesystem implementation for raw data storage."""

    def __init__(self, base_dir: Union[str, Path] = "./data/raw") -> None:
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
            # Check if directory exists
            if not await asyncio.to_thread(self.base_dir.is_dir):
                status["status"] = "error"
                status["message"] = "Base directory does not exist."
                return status
            # Check if writable by attempting to create and delete a temp file
            test_file = self.base_dir / ".health_check_test"
            await asyncio.to_thread(test_file.write_text, "test")
            await asyncio.to_thread(test_file.unlink)
        except Exception as e:
            status["status"] = "error"
            status["message"] = f"Cannot access or write to base directory: {e}"
        return status

    def _get_storage_path(self, key: str) -> Path:
        """Constructs the full path for a given key, organizing by date and type."""
        # Assuming key format like 'html/some_id' or 'json/another_id'
        # This can be made more sophisticated based on actual key structure
        parts = key.split('/')
        if len(parts) < 2:
            # Default to a generic 'misc' type if no type is provided in key
            data_type = "misc"
            file_name = key
        else:
            data_type = parts[0]
            file_name = '/'.join(parts[1:])

        today = datetime.now()
        date_path = self.base_dir / data_type / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
        return date_path / file_name

    async def save_raw(self, data: Union[str, bytes], key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Saves raw data to the local filesystem.

        Args:
            data (Union[str, bytes]): The raw data to save.
            key (str): A unique identifier for the data.
            metadata (Optional[Dict[str, Any]]): Optional metadata associated with the data.

        Returns:
            str: The key or path where the data was saved.
        """
        file_path = self._get_storage_path(key)
        await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
        if isinstance(data, str):
            await asyncio.to_thread(file_path.write_text, data, encoding="utf-8")
        else:
            await asyncio.to_thread(file_path.write_bytes, data)
        return str(file_path.relative_to(self.base_dir))

    async def load_raw(self, key: str) -> Union[str, bytes]:
        """Loads raw data from the local filesystem.

        Args:
            key (str): The unique identifier of the data to load.

        Returns:
            Union[str, bytes]: The loaded raw data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        file_path = self.base_dir / key # Key should be the relative path returned by save_raw
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"Raw data not found: {key}")
        try:
            return await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        except UnicodeDecodeError:
            return await asyncio.to_thread(file_path.read_bytes)

    async def delete_raw(self, key: str) -> None:
        """Deletes raw data from the local filesystem.

        Args:
            key (str): The unique identifier of the data to delete.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        file_path = self.base_dir / key # Key should be the relative path returned by save_raw
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"Raw data not found: {key}")
        await asyncio.to_thread(file_path.unlink)

    async def list_raw(self, prefix: Optional[str] = None) -> AsyncIterator[str]:
        """Lists raw data keys in the local filesystem.

        Args:
            prefix (Optional[str]): An optional prefix to filter the listed keys.

        Returns:
            AsyncIterator[str]: An asynchronous iterator over the keys of the raw data.
        """
        search_path = self.base_dir
        if prefix:
            search_path = self.base_dir / prefix

        for file_path in await asyncio.to_thread(lambda: list(search_path.rglob("*"))):
            if await asyncio.to_thread(file_path.is_file):
                relative_path = str(file_path.relative_to(self.base_dir))
                yield relative_path
