"""9.11 — Agent System Tests."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.agents.base_agent import AgentContext, AgentResult, AgentStep, BaseAgent
from services.agents.planner_agent import PlannerAgent
from services.agents.retrieval_agent import RetrievalAgent
from services.agents.execution_agent import ExecutionAgent
from services.agents.memory_agent import MemoryAgent
from services.agents.tool_agent import ToolAgent
from services.agents.agent_orchestrator import AgentOrchestrator


class ConcreteAgent(BaseAgent):
    """Minimal concrete agent for testing."""

    async def _execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(success=True, output=f"Processed: {context.goal}", context=context)


class TestAgentContext:
    def test_is_exhausted(self):
        ctx = AgentContext(max_iterations=3)
        ctx.iterations = 3
        assert ctx.is_exhausted()

    def test_not_exhausted_when_below_max(self):
        ctx = AgentContext(max_iterations=5)
        ctx.iterations = 2
        assert not ctx.is_exhausted()

    def test_elapsed_positive(self):
        ctx = AgentContext()
        assert ctx.elapsed() >= 0


class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_run_returns_result(self):
        agent = ConcreteAgent(name="test")
        result = await agent.run("Do something")
        assert result.success is True
        assert "Do something" in result.output

    def test_register_tool(self):
        agent = ConcreteAgent(name="test")
        agent.register_tool("my_tool", lambda: "result", "A test tool")
        assert "my_tool" in agent.list_tools()

    @pytest.mark.asyncio
    async def test_call_tool_sync(self):
        agent = ConcreteAgent(name="test")
        agent.register_tool("adder", lambda a, b: a + b, "Adds numbers")
        result = await agent._call_tool("adder", a=2, b=3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_call_tool_async(self):
        agent = ConcreteAgent(name="test")

        async def async_fn(val: str) -> str:
            return val.upper()

        agent.register_tool("upper", async_fn, "Uppercase")
        result = await agent._call_tool("upper", val="hello")
        assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_call_missing_tool_raises(self):
        agent = ConcreteAgent(name="test")
        with pytest.raises(ValueError):
            await agent._call_tool("nonexistent")

    @pytest.mark.asyncio
    async def test_run_catches_exception(self):
        class FailingAgent(BaseAgent):
            async def _execute(self, ctx: AgentContext) -> AgentResult:
                raise RuntimeError("Intentional failure")

        agent = FailingAgent(name="fail")
        result = await agent.run("goal")
        assert result.success is False
        assert result.error is not None


class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_generates_plan(self):
        agent = PlannerAgent(llm=None)
        result = await agent.run("Write a Python web scraper")
        assert result.success
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_stores_plan_in_memory(self):
        agent = PlannerAgent(llm=None)
        ctx = AgentContext(goal="test goal")
        result = await agent.run("test goal", context=ctx)
        assert "plan" in result.context.memory


class TestRetrievalAgent:
    @pytest.mark.asyncio
    async def test_runs_without_rag_service(self):
        agent = RetrievalAgent(rag_service=None)
        result = await agent.run("search for AI info")
        assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_with_mock_rag_service(self):
        mock_rag = AsyncMock()
        mock_rag.query.return_value = {
            "answer": "AI is intelligence.",
            "sources": [{"title": "AI Book", "doc_id": "d1", "score": 0.9, "snippet": "..."}],
            "context": "AI context here",
        }
        agent = RetrievalAgent(rag_service=mock_rag)
        result = await agent.run("What is AI?")
        assert result.success
        assert "AI" in result.output


class TestExecutionAgent:
    @pytest.mark.asyncio
    async def test_executes_plan_steps(self):
        agent = ExecutionAgent(llm=None)
        ctx = AgentContext(goal="test")
        ctx.memory["plan"] = ["step 1", "step 2", "step 3"]
        result = await agent.run("test goal", context=ctx)
        assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_uses_tool_when_available(self):
        agent = ExecutionAgent(llm=None)
        called = []
        agent.register_tool("search", lambda query: called.append(query) or "results", "search")
        ctx = AgentContext(goal="test")
        ctx.memory["plan"] = ["search for data"]
        result = await agent.run("test", context=ctx)
        assert isinstance(result, AgentResult)


class TestToolAgent:
    @pytest.mark.asyncio
    async def test_runs_without_tools(self):
        agent = ToolAgent(llm=None)
        result = await agent.run("do something")
        assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_runs_with_tool(self):
        agent = ToolAgent(llm=None)
        agent.register_tool("greet", lambda: "Hello!", "Greet")
        result = await agent.run("greet me")
        assert isinstance(result, AgentResult)


class TestAgentOrchestrator:
    @pytest.mark.asyncio
    async def test_run_default_pipeline(self):
        orch = AgentOrchestrator(llm=None, rag_service=None, memory_service=None)
        result = await orch.run("Explain machine learning")
        assert "goal" in result
        assert "output" in result
        assert "steps" in result

    @pytest.mark.asyncio
    async def test_register_custom_agent(self):
        orch = AgentOrchestrator()
        custom = ConcreteAgent(name="custom")
        orch.register_agent("custom", custom)
        assert "custom" in orch._agents

    def test_set_invalid_pipeline_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(ValueError):
            orch.set_pipeline(["nonexistent_agent"])

    @pytest.mark.asyncio
    async def test_parallel_run(self):
        orch = AgentOrchestrator(llm=None)
        goals = ["goal 1", "goal 2", "goal 3"]
        results = await orch.parallel_run(goals)
        assert len(results) == 3


class TestAgentStep:
    def test_defaults(self):
        step = AgentStep(action="test")
        assert step.error is None
        assert step.tool_used is None

    def test_with_tool(self):
        step = AgentStep(action="call", tool_used="search", tool_args={"q": "AI"})
        assert step.tool_used == "search"
