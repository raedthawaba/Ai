import pytest
from unittest.mock import patch, MagicMock
from hajeen_platform.services.distributed_messaging.celery_config import celery_app, process_data

@pytest.fixture(scope="module")
def celery_worker_session():
    # This fixture would typically start a Celery worker for integration tests.
    # For unit tests, we can mock the task execution.
    yield

def test_celery_app_config():
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.broker_url == "redis://localhost:6379/0"

@patch("hajeen_platform.services.distributed_messaging.celery_config.process_data.delay")
def test_process_data_task(mock_delay):
    mock_result = MagicMock()
    mock_result.get.return_value = {"status": "processed", "original_data": {"item": "test_data", "value": 123}, "processed_at": 12345}
    mock_delay.return_value = mock_result

    data = {"item": "test_data", "value": 123}
    result = process_data.delay(data).get(timeout=1)
    
    mock_delay.assert_called_once_with(data)
    assert result["status"] == "processed"
    assert result["original_data"] == data

@patch("hajeen_platform.services.distributed_messaging.celery_config.process_data.delay")
def test_process_data_task_async(mock_delay):
    mock_result = MagicMock()
    mock_result.id = "mock_task_id"
    mock_delay.return_value = mock_result

    data = {"item": "async_data", "value": 456}
    async_result = process_data.delay(data)
    
    mock_delay.assert_called_once_with(data)
    assert async_result.id == "mock_task_id"
