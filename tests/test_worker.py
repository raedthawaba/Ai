import pytest
from workers.tasks.test_task import add, ping_worker

def test_add_task():
    # Test task logic directly without needing a running worker
    result = add.apply(args=[4, 4]).get()
    assert result == 8

def test_ping_worker_task():
    result = ping_worker.apply().get()
    assert result == "pong"
