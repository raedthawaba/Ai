import os
import shutil
import pytest
import asyncio
from datetime import datetime
from pathlib import Path
from hajeen_ai_platform.data_engine.storage.processed_store.bronze_layer import BronzeLayer, BronzeSchema
from hajeen_ai_platform.data_engine.storage.processed_store.silver_layer import SilverLayer, SilverSchema
from hajeen_ai_platform.data_engine.storage.processed_store.gold_layer import GoldLayer, GoldSchema
from hajeen_ai_platform.data_engine.storage.metadata_store.sqlite_catalog import SQLiteCatalog

@pytest.fixture
def temp_processed_dir():
    dir_path = Path("./test_data_processed")
    dir_path.mkdir(parents=True, exist_ok=True)
    yield dir_path
    if dir_path.exists():
        shutil.rmtree(dir_path)

@pytest.fixture
def temp_db_path():
    db_path = Path("./test_metadata.db")
    yield db_path
    if db_path.exists():
        db_path.unlink()

@pytest.mark.asyncio
async def test_bronze_layer_save_load(temp_processed_dir):
    layer = BronzeLayer(base_dir=temp_processed_dir / "bronze")
    await layer.connect()
    
    data = {
        "id": "art_1",
        "raw_data_key": "raw/html/1.html",
        "cleaned_content": "Cleaned content here",
        "metadata": {"source": "test"}
    }
    
    key = "articles/art_1"
    saved_path = await layer.save_processed(data, key, "BronzeSchema")
    assert "articles" in saved_path
    
    loaded_data = await layer.load_processed(saved_path, "BronzeSchema")
    assert loaded_data["id"] == "art_1"
    assert loaded_data["cleaned_content"] == "Cleaned content here"
    
    await layer.disconnect()

@pytest.mark.asyncio
async def test_silver_layer_save_load(temp_processed_dir):
    layer = SilverLayer(base_dir=temp_processed_dir / "silver")
    await layer.connect()
    
    data = {
        "id": "art_1",
        "bronze_data_key": "bronze/articles/art_1.json",
        "enriched_content": "Enriched content here",
        "entities": ["AI", "Hajeen"],
        "sentiment": "positive"
    }
    
    key = "articles/art_1"
    saved_path = await layer.save_processed(data, key, "SilverSchema")
    
    loaded_data = await layer.load_processed(saved_path, "SilverSchema")
    assert loaded_data["entities"] == ["AI", "Hajeen"]
    
    await layer.disconnect()

@pytest.mark.asyncio
async def test_sqlite_catalog_operations(temp_db_path):
    catalog = SQLiteCatalog(db_path=temp_db_path)
    await catalog.connect()
    
    # Test Channel Insert
    channel_data = {
        "id": "ch_1",
        "name": "Test Channel",
        "source_type": "rss",
        "config": {"url": "http://test.com/rss"}
    }
    await catalog.insert_record("channels", channel_data)
    
    # Test Get
    record = await catalog.get_record("channels", "ch_1")
    assert record["name"] == "Test Channel"
    
    # Test Update
    await catalog.update_record("channels", "ch_1", {"description": "Updated description"})
    updated_record = await catalog.get_record("channels", "ch_1")
    assert updated_record["description"] == "Updated description"
    
    # Test Search
    results = []
    async for row in catalog.search_records("channels", filters={"source_type": "rss"}):
        results.append(row)
    assert len(results) == 1
    
    await catalog.disconnect()
