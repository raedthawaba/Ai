import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from hajeen_platform.services.production.production_manager import (
    ProductionManager,
    distributed_observability_setup,
    autoscaler,
    gpu_health_monitor,
    failure_recovery_orchestrator
)

@pytest.mark.asyncio
async def test_production_manager_init():
    manager = ProductionManager()
    assert manager is not None

@pytest.mark.asyncio
async def test_register_component():
    manager = ProductionManager()
    manager.register_component("observability", distributed_observability_setup)
    assert "observability" in manager._components

@pytest.mark.asyncio
async def test_start_monitoring():
    manager = ProductionManager()
    manager.register_component("observability_setup", distributed_observability_setup)
    manager.register_component("gpu_health", gpu_health_monitor)
    
    results = await manager.start_monitoring()
    assert "observability_setup" in results
    assert results["observability_setup"]["success"] is True
    assert "gpu_health" in results
    assert results["gpu_health"]["success"] is True

@pytest.mark.asyncio
async def test_ensure_scalability():
    manager = ProductionManager()
    manager.register_component("autoscaler", autoscaler)
    
    results = await manager.ensure_scalability(50)
    assert "autoscaler" in results
    assert results["autoscaler"]["success"] is True
    assert "Maintaining current instances" in results["autoscaler"]["action"]

    results_scaled = await manager.ensure_scalability(150)
    assert "Scaling up instances" in results_scaled["autoscaler"]["action"]

@pytest.mark.asyncio
async def test_handle_failure():
    manager = ProductionManager()
    manager.register_component("failure_recovery_orchestrator", failure_recovery_orchestrator)
    
    error_details = {"message": "Service X crashed", "code": 500}
    results = await manager.handle_failure(error_details)
    assert "failure_recovery" in results
    assert results["failure_recovery"]["success"] is True
    assert "Recovery initiated" in results["failure_recovery"]["status"]
