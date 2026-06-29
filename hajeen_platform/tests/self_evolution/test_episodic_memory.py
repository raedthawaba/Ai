import pytest
import os
import json
from unittest.mock import patch, mock_open
from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory

@pytest.fixture
def temp_memory_file(tmp_path):
    file_path = tmp_path / "test_experiences.jsonl"
    yield str(file_path)
    if os.path.exists(file_path):
        os.remove(file_path)

def test_episodic_memory_init_empty(temp_memory_file):
    memory = EpisodicMemory(storage_path=temp_memory_file)
    assert memory is not None
    assert len(memory.experiences) == 0

def test_episodic_memory_init_with_data(temp_memory_file):
    # Pre-populate the file with some data
    with open(temp_memory_file, "w") as f:
        f.write(json.dumps({"prompt": "P1", "actions": ["A1"], "outcome": "O1", "success": True}) + "\n")
        f.write(json.dumps({"prompt": "P2", "actions": ["A2"], "outcome": "O2", "success": False}) + "\n")
    
    memory = EpisodicMemory(storage_path=temp_memory_file)
    assert len(memory.experiences) == 2
    assert memory.experiences[0]["prompt"] == "P1"
    assert memory.experiences[1]["success"] is False

def test_add_experience(temp_memory_file):
    memory = EpisodicMemory(storage_path=temp_memory_file)
    memory.add_experience("Test Prompt", ["Action1"], "Test Outcome", True)
    assert len(memory.experiences) == 1
    assert memory.experiences[0]["prompt"] == "Test Prompt"
    assert os.path.exists(temp_memory_file)
    with open(temp_memory_file, "r") as f:
        data = json.loads(f.readline())
        assert data["prompt"] == "Test Prompt"

def test_retrieve_experiences_by_keyword(temp_memory_file):
    memory = EpisodicMemory(storage_path=temp_memory_file)
    memory.add_experience("Find this keyword", ["Search"], "Found it", True)
    memory.add_experience("Another prompt", ["Do something"], "Different outcome", False)
    
    results = memory.retrieve_experiences("keyword")
    assert len(results) == 1
    assert results[0]["prompt"] == "Find this keyword"

def test_get_successful_experiences(temp_memory_file):
    memory = EpisodicMemory(storage_path=temp_memory_file)
    memory.add_experience("Success 1", ["Act"], "Good", True)
    memory.add_experience("Failure 1", ["Fail"], "Bad", False)
    memory.add_experience("Success 2", ["Act again"], "Better", True)

    successful = memory.get_successful_experiences()
    assert len(successful) == 2
    assert successful[0]["prompt"] == "Success 2" # Most recent first
    assert successful[1]["prompt"] == "Success 1"

def test_get_failed_experiences(temp_memory_file):
    memory = EpisodicMemory(storage_path=temp_memory_file)
    memory.add_experience("Success 1", ["Act"], "Good", True)
    memory.add_experience("Failure 1", ["Fail"], "Bad", False)
    memory.add_experience("Success 2", ["Act again"], "Better", True)

    failed = memory.get_failed_experiences()
    assert len(failed) == 1
    assert failed[0]["prompt"] == "Failure 1"
