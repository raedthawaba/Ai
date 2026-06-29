import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from hajeen_platform.services.evaluation.evaluation_engine import EvaluationEngine
from hajeen_platform.services.evaluation.metrics import hallucination_metric, agent_success_rate_metric, latency_metric, tool_accuracy_metric
from hajeen_platform.services.agents.base_agent import AgentResult, AgentContext, AgentStep

@pytest.mark.asyncio
async def test_evaluation_engine_init():
    engine = EvaluationEngine()
    assert engine is not None

@pytest.mark.asyncio
async def test_register_metric():
    engine = EvaluationEngine()
    engine.register_metric("hallucination", hallucination_metric)
    assert "hallucination" in engine._metrics

@pytest.mark.asyncio
async def test_evaluate_agent_result():
    engine = EvaluationEngine()
    engine.register_metric("hallucination", hallucination_metric)
    engine.register_metric("success_rate", agent_success_rate_metric)
    engine.register_metric("latency", latency_metric)
    engine.register_metric("tool_accuracy", tool_accuracy_metric)

    mock_agent_result = AgentResult(
        success=True,
        output="This is a test output.",
        steps=[
            AgentStep(action="tool_call", tool_used="search", error=None),
            AgentStep(action="tool_call", tool_used="summarize", error="Error occurred"),
            AgentStep(action="tool_call", tool_used="search", error=None),
        ],
        total_duration_ms=150.5,
        context=AgentContext(goal="test", session_id="123")
    )

    results = await engine.evaluate_agent_result(mock_agent_result)
    assert "hallucination" in results
    assert results["hallucination"]["detected"] is False
    assert "success_rate" in results
    assert results["success_rate"]["success"] is True
    assert "latency" in results
    assert results["latency"]["latency_ms"] == 150.5
    assert "tool_accuracy" in results
    assert results["tool_accuracy"]["score"] == 2/3 # 2 successful tool calls out of 3

@pytest.mark.asyncio
async def test_register_benchmark():
    engine = EvaluationEngine()
    async def mock_benchmark(): return {"score": 0.8}
    engine.register_benchmark("mock_benchmark", mock_benchmark)
    assert "mock_benchmark" in engine._benchmarks

@pytest.mark.asyncio
async def test_run_benchmark():
    engine = EvaluationEngine()
    async def mock_benchmark(): return {"score": 0.8}
    engine.register_benchmark("mock_benchmark", mock_benchmark)
    
    results = await engine.run_benchmark("mock_benchmark")
    assert results["success"] is True
    assert results["results"]["score"] == 0.8

@pytest.mark.asyncio
async def test_run_all_benchmarks():
    engine = EvaluationEngine()
    async def mock_benchmark1(): return {"score": 0.7}
    async def mock_benchmark2(): return {"score": 0.9}
    engine.register_benchmark("mock_benchmark1", mock_benchmark1)
    engine.register_benchmark("mock_benchmark2", mock_benchmark2)

    results = await engine.run_all_benchmarks()
    assert "mock_benchmark1" in results
    assert results["mock_benchmark1"]["results"]["score"] == 0.7
    assert "mock_benchmark2" in results
    assert results["mock_benchmark2"]["results"]["score"] == 0.9
