import pytest
import os
import shutil
from pathlib import Path
from data_engine.channels.predefined.demo_channel import DemoChannel
from shared.schemas.channel import ChannelConfig, SourceConfig, ScheduleConfig, ChannelStatus
from data_engine.storage.storage_manager import StorageManager

@pytest.fixture
def temp_data_dir(tmp_path):
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    yield data_dir
    if data_dir.exists():
        shutil.rmtree(data_dir)

@pytest.mark.asyncio
async def test_demo_channel_storage_integration(temp_data_dir):
    # 1. Setup
    storage_manager = StorageManager(base_data_dir=temp_data_dir)
    
    config = ChannelConfig(
        id="test_demo_ch",
        name="Test Demo Channel",
        status=ChannelStatus.ACTIVE,
        source=SourceConfig(url="https://example.com", type="demo"),
        schedule=ScheduleConfig(cron="0 * * * *")
    )
    
    channel = DemoChannel(config=config, storage_manager=storage_manager)
    
    # 2. Execute
    fetch_result = await channel.fetch()
    assert len(fetch_result.articles) > 0
    
    processed_articles = await channel.run_pipeline(fetch_result.articles)
    assert len(processed_articles) == len(fetch_result.articles)
    
    # 3. Verify Storage
    # Check Raw Storage
    raw_files = list((temp_data_dir / "raw" / "api").rglob("*.json"))
    assert len(raw_files) == len(fetch_result.articles)
    
    # Check Bronze Storage
    bronze_files = list((temp_data_dir / "processed" / "bronze" / "articles").rglob("*.json"))
    assert len(bronze_files) == len(fetch_result.articles)
    
    # Check Metadata Catalog (SQLite)
    await storage_manager.connect()
    try:
        for article in fetch_result.articles:
            record = await storage_manager.get_article(article.id)
            assert record is not None
            assert record["id"] == article.id
            assert record["channel_id"] == config.id
            assert record["title"] == article.title
            assert "raw_data_key" in record
            assert "bronze_data_key" in record
    finally:
        await storage_manager.disconnect()
