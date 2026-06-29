import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from hajeen_platform.services.self_evolution.curiosity_engine import CuriosityEngine
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine
from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory

@pytest.fixture
def mock_llm_inference_function():
    return AsyncMock()

@pytest.fixture
def mock_reflection_engine():
    return MagicMock(spec=SelfReflectionEngine)

@pytest.fixture
def mock_episodic_memory():
    return MagicMock(spec=EpisodicMemory)

@pytest.fixture
def curiosity_engine(mock_llm_inference_function, mock_reflection_engine, mock_episodic_memory):
    return CuriosityEngine(
        llm_inference_function=mock_llm_inference_function,
        reflection_engine=mock_reflection_engine,
        episodic_memory=mock_episodic_memory,
        exploration_threshold=0.3
    )

@pytest.mark.asyncio
async def test_decide_to_explore_low_confidence(curiosity_engine):
    should_explore = await curiosity_engine.decide_to_explore(
        current_task_context={}, agent_confidence=0.2, recent_failures=0
    )
    assert should_explore is True

@pytest.mark.asyncio
async def test_decide_to_explore_repeated_failures(curiosity_engine):
    should_explore = await curiosity_engine.decide_to_explore(
        current_task_context={}, agent_confidence=0.5, recent_failures=3
    )
    assert should_explore is True

@pytest.mark.asyncio
async def test_decide_to_explore_no_exploration(curiosity_engine):
    should_explore = await curiosity_engine.decide_to_explore(
        current_task_context={}, agent_confidence=0.7, recent_failures=0
    )
    assert should_explore is False

@pytest.mark.asyncio
async def test_suggest_exploration_strategy(curiosity_engine, mock_llm_inference_function):
    mock_llm_inference_function.return_value = '{"strategy_description": "Try new tools", "suggested_actions": ["Use Tool A", "Use Tool B"]}'
    strategy = await curiosity_engine.suggest_exploration_strategy(
        current_task_context={"problem": "stuck"}, available_tools=["Tool A", "Tool B"]
    )
    assert "strategy_description" in strategy
    assert "suggested_actions" in strategy
    mock_llm_inference_function.assert_called_once()

@pytest.mark.asyncio
async def test_evaluate_exploration_outcome(curiosity_engine, mock_llm_inference_function):
    mock_llm_inference_function.return_value = '{"evaluation_summary": "Very useful", "success_score": 4, "lessons_learned": ["Learned X"]}'
    outcome = await curiosity_engine.evaluate_exploration_outcome(
        exploration_strategy={"strategy_description": "test"}, exploration_results="some results"
    )
    assert "evaluation_summary" in outcome
    assert outcome["success_score"] == 4
    mock_llm_inference_function.assert_called_once()

@pytest.mark.asyncio
async def test_suggest_exploration_strategy_error_handling(curiosity_engine, mock_llm_inference_function):
    mock_llm_inference_function.side_effect = Exception("LLM Error")
    strategy = await curiosity_engine.suggest_exploration_strategy(
        current_task_context={"problem": "stuck"}, available_tools=["Tool A"]
    )
    assert "error" in strategy
    assert "LLM Error" in strategy["error"]
    assert "Failed to generate strategy." in strategy["strategy_description"]
