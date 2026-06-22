import asyncio
from hajeen_ai_platform.data_engine.storage.metadata_store.sqlite_catalog import SQLiteCatalog
from hajeen_ai_platform.data_engine.storage.storage_manager import StorageManager

async def initialize_database():
    """Initializes the SQLite database by connecting the SQLiteCatalog."""
    print("Initializing SQLite database...")
    # Use StorageManager to ensure all components are initialized correctly
    storage_manager = StorageManager()
    await storage_manager.metadata_catalog.connect()
    print(f"Database initialized at: {storage_manager.metadata_catalog.db_path}")

if __name__ == "__main__":
    asyncio.run(initialize_database())
