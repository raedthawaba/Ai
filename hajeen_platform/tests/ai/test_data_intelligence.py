import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from hajeen_platform.services.data_intelligence.data_factory import AutonomousDataFactory
from hajeen_platform.services.data_intelligence.components import (
    synthetic_data_generator,
    dataset_refiner,
    vector_store_ingestion_pipeline,
    MockLLM,
    MockVectorDBClient
)

@pytest.mark.asyncio
async def test_autonomous_data_factory_init():
    factory = AutonomousDataFactory()
    assert factory is not None

@pytest.mark.asyncio
async def test_register_generator():
    factory = AutonomousDataFactory()
    factory.register_generator("synth_gen", synthetic_data_generator)
    assert "synth_gen" in factory._generators

@pytest.mark.asyncio
async def test_generate_data():
    mock_llm = MockLLM()
    factory = AutonomousDataFactory(llm=mock_llm)
    factory.register_generator("synth_gen", synthetic_data_generator)
    
    schema = {"field1": "string", "field2": "int"}
    data = await factory.generate_data("synth_gen", {"schema": schema, "count": 2})
    assert len(data) == 2
    assert "synth_0" in data[0]["id"]

@pytest.mark.asyncio
async def test_register_refiner():
    factory = AutonomousDataFactory()
    factory.register_refiner("cleaner", dataset_refiner)
    assert "cleaner" in factory._refiners

@pytest.mark.asyncio
async def test_refine_dataset():
    mock_llm = MockLLM()
    factory = AutonomousDataFactory(llm=mock_llm)
    factory.register_refiner("cleaner", dataset_refiner)
    
    initial_data = [{"id": "1", "value": 10}]
    refined_data = await factory.refine_dataset("cleaner", initial_data, {"rules": ["remove_duplicates"]})
    assert len(refined_data) == 1
    assert refined_data[0]["refined"] is True

@pytest.mark.asyncio
async def test_register_ingestion_pipeline():
    factory = AutonomousDataFactory()
    factory.register_ingestion_pipeline("vector_ingest", vector_store_ingestion_pipeline)
    assert "vector_ingest" in factory._ingestion_pipelines

@pytest.mark.asyncio
async def test_ingest_data():
    factory = AutonomousDataFactory()
    factory.register_ingestion_pipeline("vector_ingest", vector_store_ingestion_pipeline)
    mock_db_client = MockVectorDBClient()
    
    data_to_ingest = [{"id": "vec_1", "vector": [0.1, 0.2]}]
    result = await factory.ingest_data("vector_ingest", data_to_ingest, {"vector_db_client": mock_db_client})
    assert result["status"] == "success"
    assert result["ingested_count"] == 1

@pytest.mark.asyncio
async def test_run_autonomous_loop():
    mock_llm = MockLLM()
    factory = AutonomousDataFactory(llm=mock_llm)
    factory.register_generator("default_generator", synthetic_data_generator)
    factory.register_refiner("default_refiner", dataset_refiner)
    factory.register_ingestion_pipeline("default_ingestion", AsyncMock(return_value={"status": "success"}))

    config = {
        "generator": "default_generator",
        "generator_config": {"schema": {"name": "str"}, "count": 1},
        "refiner": "default_refiner",
        "refiner_config": {"rules": ["clean"]},
        "ingestion_pipeline": "default_ingestion",
        "ingestion_config": {"vector_db_client": MockVectorDBClient()}
    }

    final_dataset = await factory.run_autonomous_loop(config, iterations=2)
    assert final_dataset is not None
    assert final_dataset[0]["refined"] is True
    factory._ingestion_pipelines["default_ingestion"].assert_called()
