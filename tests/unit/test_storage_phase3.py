import os
import shutil
import pytest
import asyncio
from pathlib import Path
from hajeen_ai_platform.data_engine.storage.raw_store.local_storage import LocalRawStorage

@pytest.fixture
def temp_storage_dir():
    dir_path = Path("./test_data_raw")
    dir_path.mkdir(parents=True, exist_ok=True)
    yield dir_path
    if dir_path.exists():
        shutil.rmtree(dir_path)

@pytest.mark.asyncio
async def test_local_raw_storage_save_load(temp_storage_dir):
    storage = LocalRawStorage(base_dir=temp_storage_dir)
    await storage.connect()
    
    test_data = "<html><body>Hello World</body></html>"
    test_key = "html/test_article.html"
    
    # Save
    saved_path = await storage.save_raw(test_data, test_key)
    assert "html" in saved_path
    assert "test_article.html" in saved_path
    
    # Load
    loaded_data = await storage.load_raw(saved_path)
    assert loaded_data == test_data
    
    await storage.disconnect()

@pytest.mark.asyncio
async def test_local_raw_storage_delete(temp_storage_dir):
    storage = LocalRawStorage(base_dir=temp_storage_dir)
    await storage.connect()
    
    test_data = '{"key": "value"}'
    test_key = "json/test_data.json"
    
    saved_path = await storage.save_raw(test_data, test_key)
    assert (temp_storage_dir / saved_path).exists()
    
    # Delete
    await storage.delete_raw(saved_path)
    assert not (temp_storage_dir / saved_path).exists()
    
    await storage.disconnect()

@pytest.mark.asyncio
async def test_local_raw_storage_list(temp_storage_dir):
    storage = LocalRawStorage(base_dir=temp_storage_dir)
    await storage.connect()
    
    await storage.save_raw("data1", "api/call1.json")
    await storage.save_raw("data2", "api/call2.json")
    await storage.save_raw("data3", "rss/feed1.xml")
    
    items = []
    async for item in storage.list_raw():
        items.append(item)
    
    assert len(items) == 3
    
    api_items = []
    async for item in storage.list_raw(prefix="api"):
        api_items.append(item)
    
    assert len(api_items) == 2
    
    await storage.disconnect()

@pytest.mark.asyncio
async def test_local_raw_storage_health_check(temp_storage_dir):
    storage = LocalRawStorage(base_dir=temp_storage_dir)
    health = await storage.health_check()
    assert health["status"] == "ok"
    assert health["path"] == str(temp_storage_dir.resolve())
