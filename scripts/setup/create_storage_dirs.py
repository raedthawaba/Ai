import asyncio
from hajeen_ai_platform.data_engine.storage.storage_manager import StorageManager

async def create_storage_directories():
    """Ensures that all necessary storage directories are created."""
    print("Creating storage directories...")
    storage_manager = StorageManager()
    await storage_manager.raw_storage.connect()
    await storage_manager.bronze_layer.connect()
    await storage_manager.silver_layer.connect()
    await storage_manager.gold_layer.connect()
    print(f"Raw storage directory: {storage_manager.raw_storage.base_dir}")
    print(f"Bronze layer directory: {storage_manager.bronze_layer.base_dir}")
    print(f"Silver layer directory: {storage_manager.silver_layer.base_dir}")
    print(f"Gold layer directory: {storage_manager.gold_layer.base_dir}")

if __name__ == "__main__":
    asyncio.run(create_storage_directories())
