import pytest
import asyncio
from unittest.mock import AsyncMock
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine, MockLLM

@pytest.mark.asyncio
async def test_self_reflection_engine_init():
    mock_llm = MockLLM()
    engine = SelfReflectionEngine(mock_llm)
    assert engine is not None
    assert engine.llm_inference_function == mock_llm

@pytest.mark.asyncio
async def test_reflect_on_output():
    mock_llm = MockLLM()
    engine = SelfReflectionEngine(mock_llm)
    
    original_prompt = "Summarize this document."
    agent_output = "This is a summary of the document."
    criteria = ["accuracy", "completeness"]
    
    reflection_result = await engine.reflect_on_output(original_prompt, agent_output, criteria)
    
    assert "scores" in reflection_result
    assert reflection_result["scores"]["accuracy"] == 4
    assert "critique" in reflection_result
    assert "Output was mostly accurate but lacked some details." in reflection_result["critique"]
    assert "improvements" in reflection_result
    assert "Add more details to X." in reflection_result["improvements"][0]

@pytest.mark.asyncio
async def test_critique_plan():
    mock_llm = MockLLM()
    engine = SelfReflectionEngine(mock_llm)
    
    original_goal = "Develop a new feature."
    agent_plan = ["Step 1: Research", "Step 2: Design", "Step 3: Implement"]
    criteria = ["logic", "efficiency"]
    
    critique_result = await engine.critique_plan(original_goal, agent_plan, criteria)
    
    assert "scores" in critique_result
    assert critique_result["scores"]["logic"] == 4
    assert "critique" in critique_result
    assert "Plan is logical but could be more efficient." in critique_result["critique"]
    assert "improvements" in critique_result
    assert "Combine steps Y and Z." in critique_result["improvements"][0]

@pytest.mark.asyncio
async def test_reflection_error_handling():
    mock_llm = AsyncMock(side_effect=Exception("LLM API Error"))
    engine = SelfReflectionEngine(mock_llm)
    
    original_prompt = "Test prompt."
    agent_output = "Test output."
    criteria = ["test_criterion"]
    
    reflection_result = await engine.reflect_on_output(original_prompt, agent_output, criteria)
    
    assert "error" in reflection_result
    assert "LLM API Error" in reflection_result["error"]
    assert "Failed to perform self-reflection." in reflection_result["critique"]
