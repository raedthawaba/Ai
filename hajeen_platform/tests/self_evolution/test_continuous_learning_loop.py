import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from hajeen_platform.services.self_evolution.continuous_learning_loop import ContinuousLearningLoop
from hajeen_platform.services.self_evolution.self_reflection_engine import SelfReflectionEngine
from hajeen_platform.services.self_evolution.episodic_memory import EpisodicMemory
from hajeen_platform.services.self_evolution.curiosity_engine import CuriosityEngine

@pytest.fixture
def mock_llm_inference_function():
    return AsyncMock()

@pytest.fixture
def mock_reflection_engine():
    mock = MagicMock(spec=SelfReflectionEngine)
    mock.reflect_on_output = AsyncMock(return_value={
        "scores": {"accuracy": 4, "completeness": 4, "relevance": 4},
        "critique": "Good output.",
        "improvements": []
    })
    return mock

@pytest.fixture
def mock_episodic_memory():
    mock = MagicMock(spec=EpisodicMemory)
    mock.add_experience = MagicMock()
    mock.get_failed_experiences = MagicMock(return_value=[])
    return mock

@pytest.fixture
def mock_curiosity_engine():
    mock = MagicMock(spec=CuriosityEngine)
    mock.decide_to_explore = AsyncMock(return_value=False)
    mock.suggest_exploration_strategy = AsyncMock(return_value={
        "strategy_description": "Explore new path",
        "suggested_actions": ["Action X"]
    })
    return mock

@pytest.fixture
def continuous_learning_loop(
    mock_llm_inference_function, mock_reflection_engine, mock_episodic_memory, mock_curiosity_engine
):
    return ContinuousLearningLoop(
        llm_inference_function=mock_llm_inference_function,
        reflection_engine=mock_reflection_engine,
        episodic_memory=mock_episodic_memory,
        curiosity_engine=mock_curiosity_engine,
    )

@pytest.mark.asyncio
async def test_execute_and_learn_success(continuous_learning_loop, mock_reflection_engine, mock_episodic_memory, mock_curiosity_engine):
    async def mock_agent_action_function(prompt, tools):
        return {"output": "Task completed successfully.", "success": True, "confidence": 0.9, "actions_taken": ["Action1"]}

    task_prompt = "Perform a simple task."
    available_tools = ["ToolA"]

    result = await continuous_learning_loop.execute_and_learn(task_prompt, mock_agent_action_function, available_tools)

    assert result["status"] == "completed"
    assert result["original_output"]["success"] is True
    mock_reflection_engine.reflect_on_output.assert_called_once()
    mock_episodic_memory.add_experience.assert_called_once()
    mock_curiosity_engine.decide_to_explore.assert_called_once()
    mock_curiosity_engine.suggest_exploration_strategy.assert_not_called()

@pytest.mark.asyncio
async def test_execute_and_learn_failure_triggers_exploration(continuous_learning_loop, mock_reflection_engine, mock_episodic_memory, mock_curiosity_engine):
    async def mock_agent_action_function(prompt, tools):
        return {"output": "Task failed.", "success": False, "confidence": 0.2, "actions_taken": ["Action1"]}

    mock_reflection_engine.reflect_on_output.return_value = {
        "scores": {"accuracy": 2, "completeness": 2, "relevance": 2},
        "critique": "Poor output.",
        "improvements": ["Try again"]
    }
    mock_curiosity_engine.decide_to_explore.return_value = True

    task_prompt = "Perform a complex task."
    available_tools = ["ToolA", "ToolB"]

    result = await continuous_learning_loop.execute_and_learn(task_prompt, mock_agent_action_function, available_tools)

    assert result["status"] == "exploration_suggested"
    assert result["original_output"]["success"] is False
    mock_reflection_engine.reflect_on_output.assert_called_once()
    assert mock_episodic_memory.add_experience.call_count == 2
    # Verify the first call is for the task
    task_experience = mock_episodic_memory.add_experience.call_args_list[0].kwargs
    assert task_experience["prompt"] == task_prompt
    assert task_experience["success"] is False
    # Verify the second call is for the exploration strategy
    exploration_experience = mock_episodic_memory.add_experience.call_args_list[1].kwargs
    assert "Exploration for:" in exploration_experience["prompt"]
    assert exploration_experience["metadata"]["type"] == "exploration_strategy"
    mock_curiosity_engine.decide_to_explore.assert_called_once()
    mock_curiosity_engine.suggest_exploration_strategy.assert_called_once()
    assert "exploration_strategy" in result

@pytest.mark.asyncio
async def test_execute_and_learn_low_confidence_triggers_exploration(continuous_learning_loop, mock_reflection_engine, mock_episodic_memory, mock_curiosity_engine):
    async def mock_agent_action_function(prompt, tools):
        return {"output": "Task completed with low confidence.", "success": True, "confidence": 0.1, "actions_taken": ["Action1"]}

    mock_curiosity_engine.decide_to_explore.return_value = True

    task_prompt = "Perform a task with uncertainty."
    available_tools = ["ToolC"]

    result = await continuous_learning_loop.execute_and_learn(task_prompt, mock_agent_action_function, available_tools)

    assert result["status"] == "exploration_suggested"
    mock_curiosity_engine.decide_to_explore.assert_called_once()
    mock_curiosity_engine.suggest_exploration_strategy.assert_called_once()

@pytest.mark.asyncio
async def test_execute_and_learn_reflection_overrides_success(continuous_learning_loop, mock_reflection_engine, mock_episodic_memory, mock_curiosity_engine):
    async def mock_agent_action_function(prompt, tools):
        return {"output": "Seems successful.", "success": True, "confidence": 0.8, "actions_taken": ["Action1"]}

    mock_reflection_engine.reflect_on_output.return_value = {
        "scores": {"accuracy": 1, "completeness": 1, "relevance": 1},
        "critique": "Completely wrong.",
        "improvements": ["Restart"]
    }
    mock_curiosity_engine.decide_to_explore.return_value = True # Assume exploration triggered by low reflection score

    task_prompt = "Task that looks successful but isn't."
    available_tools = ["ToolD"]

    result = await continuous_learning_loop.execute_and_learn(task_prompt, mock_agent_action_function, available_tools)

    assert result["status"] == "exploration_suggested"
    # The initial agent_output said success=True, but reflection changed it to False for memory storage
    assert mock_episodic_memory.add_experience.call_count == 2
    # Verify the first call is for the task
    task_experience = mock_episodic_memory.add_experience.call_args_list[0].kwargs
    assert task_experience["prompt"] == task_prompt
    assert task_experience["success"] is False
    # Verify the second call is for the exploration strategy
    exploration_experience = mock_episodic_memory.add_experience.call_args_list[1].kwargs
    assert "Exploration for:" in exploration_experience["prompt"]
    assert exploration_experience["metadata"]["type"] == "exploration_strategy"
    stored_experience = task_experience
    assert stored_experience["success"] is False
    mock_curiosity_engine.decide_to_explore.assert_called_once()
