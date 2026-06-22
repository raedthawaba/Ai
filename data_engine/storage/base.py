
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Union

class BaseStorage(ABC):
    """Abstract base class for all storage systems."""

    @abstractmethod
    async def connect(self) -> None:
        """Establishes a connection to the storage system."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Closes the connection to the storage system."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Performs a health check on the storage system.

        Returns:
            Dict[str, Any]: A dictionary containing health status information.
        """
        pass

class BaseRawStorage(BaseStorage):
    """Abstract base class for raw data storage."""

    @abstractmethod
    async def save_raw(self, data: Union[str, bytes], key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Saves raw data to the storage.

        Args:
            data (Union[str, bytes]): The raw data to save.
            key (str): A unique identifier for the data.
            metadata (Optional[Dict[str, Any]]): Optional metadata associated with the data.

        Returns:
            str: The key or path where the data was saved.
        """
        pass

    @abstractmethod
    async def load_raw(self, key: str) -> Union[str, bytes]:
        """Loads raw data from the storage.

        Args:
            key (str): The unique identifier of the data to load.

        Returns:
            Union[str, bytes]: The loaded raw data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        pass

    @abstractmethod
    async def delete_raw(self, key: str) -> None:
        """Deletes raw data from the storage.

        Args:
            key (str): The unique identifier of the data to delete.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        pass

    @abstractmethod
    async def list_raw(self, prefix: Optional[str] = None) -> AsyncIterator[str]:
        """Lists raw data keys in the storage.

        Args:
            prefix (Optional[str]): An optional prefix to filter the listed keys.

        Returns:
            AsyncIterator[str]: An asynchronous iterator over the keys of the raw data.
        """
        pass

class BaseProcessedStorage(BaseStorage):
    """Abstract base class for processed data storage."""

    @abstractmethod
    async def save_processed(self, data: Dict[str, Any], key: str, schema_name: str, version: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Saves processed data to the storage.

        Args:
            data (Dict[str, Any]): The processed data to save.
            key (str): A unique identifier for the data.
            schema_name (str): The name of the schema used for validation.
            version (Optional[str]): Optional version of the data.
            metadata (Optional[Dict[str, Any]]): Optional metadata associated with the data.

        Returns:
            str: The key or path where the data was saved.
        """
        pass

    @abstractmethod
    async def load_processed(self, key: str, schema_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Loads processed data from the storage.

        Args:
            key (str): The unique identifier of the data to load.
            schema_name (str): The name of the schema used for validation.
            version (Optional[str]): Optional version of the data.

        Returns:
            Dict[str, Any]: The loaded processed data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
            ValidationError: If the loaded data does not conform to the specified schema.
        """
        pass

    @abstractmethod
    async def delete_processed(self, key: str, schema_name: str, version: Optional[str] = None) -> None:
        """Deletes processed data from the storage.

        Args:
            key (str): The unique identifier of the data to delete.
            schema_name (str): The name of the schema used for validation.
            version (Optional[str]): Optional version of the data.

        Raises:
            FileNotFoundError: If the data with the given key is not found.
        """
        pass

    @abstractmethod
    async def list_processed(self, schema_name: str, prefix: Optional[str] = None) -> AsyncIterator[str]:
        """Lists processed data keys in the storage.

        Args:
            schema_name (str): The name of the schema to filter by.
            prefix (Optional[str]): An optional prefix to filter the listed keys.

        Returns:
            AsyncIterator[str]: An asynchronous iterator over the keys of the processed data.
        """
        pass

class BaseMetadataStore(BaseStorage):
    """Abstract base class for metadata storage."""

    @abstractmethod
    async def create_table(self, table_name: str, schema: Dict[str, Any]) -> None:
        """Creates a table in the metadata store.

        Args:
            table_name (str): The name of the table to create.
            schema (Dict[str, Any]): A dictionary defining the table schema.
        """
        pass

    @abstractmethod
    async def insert_record(self, table_name: str, record: Dict[str, Any]) -> Any:
        """Inserts a record into a table.

        Args:
            table_name (str): The name of the table.
            record (Dict[str, Any]): The record to insert.

        Returns:
            Any: The ID or primary key of the inserted record.
        """
        pass

    @abstractmethod
    async def update_record(self, table_name: str, record_id: Any, updates: Dict[str, Any]) -> None:
        """Updates a record in a table.

        Args:
            table_name (str): The name of the table.
            record_id (Any): The ID of the record to update.
            updates (Dict[str, Any]): A dictionary of fields to update.

        Raises:
            RecordNotFoundError: If the record with the given ID is not found.
        """
        pass

    @abstractmethod
    async def get_record(self, table_name: str, record_id: Any) -> Optional[Dict[str, Any]]:
        """Retrieves a record from a table.

        Args:
            table_name (str): The name of the table.
            record_id (Any): The ID of the record to retrieve.

        Returns:
            Optional[Dict[str, Any]]: The record as a dictionary, or None if not found.
        """
        pass

    @abstractmethod
    async def search_records(self, table_name: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> AsyncIterator[Dict[str, Any]]:
        """Searches for records in a table based on filters.

        Args:
            table_name (str): The name of the table.
            filters (Optional[Dict[str, Any]]): A dictionary of filters to apply.
            limit (Optional[int]): The maximum number of records to return.

        Returns:
            AsyncIterator[Dict[str, Any]]: An asynchronous iterator over the matching records.
        """
        pass

    @abstractmethod
    async def delete_record(self, table_name: str, record_id: Any) -> None:
        """Deletes a record from a table.

        Args:
            table_name (str): The name of the table.
            record_id (Any): The ID of the record to delete.

        Raises:
            RecordNotFoundError: If the record with the given ID is not found.
        """
        pass

