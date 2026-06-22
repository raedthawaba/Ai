from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Union

class IStorage(Protocol):
    """Interface for basic storage operations."""

    async def save(self, data: Union[str, bytes, Dict[str, Any]], key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Saves data to the storage.

        Args:
            data (Union[str, bytes, Dict[str, Any]]): The data to save.
            key (str): A unique identifier for the data.
            metadata (Optional[Dict[str, Any]]): Optional metadata associated with the data.

        Returns:
            str: The key or path where the data was saved.
        """
        ...

    async def load(self, key: str) -> Union[str, bytes, Dict[str, Any]]:
        """Loads data from the storage.

        Args:
            key (str): The unique identifier of the data to load.

        Returns:
            Union[str, bytes, Dict[str, Any]]: The loaded data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        ...

    async def delete(self, key: str) -> None:
        """Deletes data from the storage.

        Args:
            key (str): The unique identifier of the data to delete.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Checks if data with the given key exists in the storage.

        Args:
            key (str): The unique identifier of the data to check.

        Returns:
            bool: True if the data exists, False otherwise.
        """
        ...

    async def list_items(self, prefix: Optional[str] = None) -> AsyncIterator[str]:
        """Lists data keys in the storage.

        Args:
            prefix (Optional[str]): An optional prefix to filter the listed keys.

        Returns:
            AsyncIterator[str]: An asynchronous iterator over the keys of the data.
        """
        ...
