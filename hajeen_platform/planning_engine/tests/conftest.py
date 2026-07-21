"""Pytest configuration for Planning Engine tests."""
import asyncio
import sys
from pathlib import Path

import pytest

# Add the planning_engine to the path
planning_engine_path = Path(__file__).parent.parent
sys.path.insert(0, str(planning_engine_path))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    # Import modules that have singletons
    try:
        from planning_engine.core import engine as engine_module
        from planning_engine.config import manager as config_module
        from planning_engine.execution import trace as trace_module
        from planning_engine.metrics import collector as metrics_module
        from planning_engine.error_recovery import recovery as recovery_module
        from planning_engine.di import container as di_module
        from planning_engine.plugins import manager as plugins_module
        from planning_engine.registry import service as registry_module
        
        # Reset singletons
        engine_module._engine = None
        config_module._config_manager = None
        trace_module._trace_manager = None
        metrics_module._metrics_collector = None
        recovery_module._error_recovery_manager = None
        di_module._container = None
        plugins_module._plugin_manager = None
        registry_module._registry = None
        
    except ImportError:
        pass
    
    yield


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary log directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir
