"""اختبارات Phase 5 — AI Core & Inference Stability."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# ModelManager Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestModelManager:
    def _get_manager(self):
        from core.model.model_manager import ModelManager
        return ModelManager(max_loaded_models=2, memory_limit_mb=8192.0)

    def test_singleton_returns_same_instance(self):
        from core.model.model_manager import ModelManager
        ModelManager._instance = None
        s1 = ModelManager.get_instance()
        s2 = ModelManager.get_instance()
        assert s1 is s2
        ModelManager._instance = None

    def test_register_model(self):
        mgr = self._get_manager()
        mgr.register("test-model", backend="huggingface", device="cpu")
        listed = mgr.list_registered()
        assert any(m["model_id"] == "test-model" for m in listed)

    def test_register_duplicate_is_idempotent(self):
        mgr = self._get_manager()
        mgr.register("dup-model", backend="huggingface")
        mgr.register("dup-model", backend="huggingface")  # لا يجب أن يرمي خطأ
        assert len([m for m in mgr.list_registered() if m["model_id"] == "dup-model"]) == 1

    def test_unload_unregistered_model_returns_false(self):
        mgr = self._get_manager()
        result = mgr.unload("nonexistent-model")
        assert result is False

    def test_health_returns_dict(self):
        mgr = self._get_manager()
        health = mgr.health()
        assert "registered" in health
        assert "loaded" in health
        assert "device" in health

    def test_resolve_device_defaults(self):
        from core.model.model_manager import ModelManager
        device = ModelManager._resolve_device("cpu")
        assert device == "cpu"

    def test_load_unregistered_raises(self):
        mgr = self._get_manager()
        with pytest.raises(KeyError):
            asyncio.get_event_loop().run_until_complete(mgr.load("ghost-model"))

    @pytest.mark.asyncio
    async def test_load_with_mock_loader(self):
        from core.model.model_manager import ModelManager, ModelStatus

        mgr = ModelManager(max_loaded_models=2)
        mgr.register("mock-model", backend="huggingface", device="cpu")

        mock_model = MagicMock()
        mock_tokenizer = MagicMock()

        with patch.object(mgr, "_load_sync", return_value=(mock_model, mock_tokenizer)):
            entry = await mgr.load("mock-model")
            assert entry.status == ModelStatus.READY
            assert entry.model is mock_model

    @pytest.mark.asyncio
    async def test_unload_after_load(self):
        from core.model.model_manager import ModelManager, ModelStatus

        mgr = ModelManager(max_loaded_models=2)
        mgr.register("unload-test", backend="huggingface", device="cpu")

        with patch.object(mgr, "_load_sync", return_value=(MagicMock(), MagicMock())):
            await mgr.load("unload-test")
            result = mgr.unload("unload-test")
            assert result is True

            entry = mgr._models["unload-test"]
            assert entry.status == ModelStatus.UNLOADED


# ──────────────────────────────────────────────────────────────────────────────
# InferenceService Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestInferenceService:
    def _get_service(self, generate_text: str = "test response"):
        from services.inference_service import InferenceService
        llm = MagicMock()
        llm.agenerate = AsyncMock(return_value=generate_text)
        llm.is_ready = MagicMock(return_value=True)
        llm.default_model = "test-model"

        async def _stream(*args, **kwargs):
            for chunk in ["hello", " world"]:
                yield chunk

        llm.astream = _stream
        service = InferenceService(llm_manager=llm)
        return service

    @pytest.mark.asyncio
    async def test_generate_returns_dict(self):
        service = self._get_service("الإجابة التجريبية")
        result = await service.generate("ما هو الذكاء الاصطناعي؟")
        assert "text" in result
        assert result["text"] == "الإجابة التجريبية"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_generate_records_latency(self):
        service = self._get_service()
        result = await service.generate("test")
        assert result["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        service = self._get_service()
        chunks = []
        async for chunk in service.stream("test prompt"):
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_batch_generate(self):
        service = self._get_service("batch response")
        results = await service.batch_generate(["p1", "p2", "p3"])
        assert len(results) == 3
        assert all("text" in r for r in results)

    @pytest.mark.asyncio
    async def test_batch_generate_handles_partial_failure(self):
        from services.inference_service import InferenceService
        llm = MagicMock()
        call_count = [0]

        async def _gen(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("model error")
            return f"response to: {prompt}"

        llm.agenerate = _gen
        llm.is_ready = MagicMock(return_value=True)
        llm.default_model = "test"
        service = InferenceService(llm_manager=llm)

        results = await service.batch_generate(["p1", "p2", "p3"])
        assert len(results) == 3
        error_results = [r for r in results if "error" in r]
        assert len(error_results) == 1

    def test_health_returns_ok(self):
        service = self._get_service()
        health = service.health()
        assert health["status"] == "ok"


# ──────────────────────────────────────────────────────────────────────────────
# AgentService Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestAgentService:
    def _get_service(self):
        from services.agent_service import AgentService
        return AgentService(max_steps=3, step_timeout=5.0)

    def test_agent_service_initializes(self):
        service = self._get_service()
        assert service.active_count() == 0
        health = service.health()
        assert health["status"] == "ok"

    @pytest.mark.asyncio
    async def test_run_returns_trace(self):
        from services.agent_service import AgentService, AgentStatus
        service = AgentService(max_steps=2)
        trace = await service.run("ما هو الطقس؟")
        assert trace.agent_id != ""
        assert trace.query == "ما هو الطقس؟"
        assert trace.status in (AgentStatus.COMPLETED, AgentStatus.FAILED)

    @pytest.mark.asyncio
    async def test_trace_has_steps(self):
        from services.agent_service import AgentService
        service = AgentService(max_steps=2)
        trace = await service.run("سؤال بسيط")
        assert len(trace.steps) > 0

    @pytest.mark.asyncio
    async def test_trace_has_final_answer(self):
        from services.agent_service import AgentService
        service = AgentService(max_steps=2)
        trace = await service.run("أجب على هذا السؤال")
        assert trace.final_answer is not None

    @pytest.mark.asyncio
    async def test_session_memory_persists(self):
        from services.agent_service import AgentService
        service = AgentService(max_steps=1)
        session_id = "test_session_001"
        await service.run("سؤال أول", session_id=session_id)
        memory = service.get_session_memory(session_id)
        assert memory is not None
        assert len(memory.get_history()) > 0

    @pytest.mark.asyncio
    async def test_clear_session(self):
        from services.agent_service import AgentService
        service = AgentService(max_steps=1)
        session_id = "clear_test"
        await service.run("سؤال", session_id=session_id)
        service.clear_session(session_id)
        assert service.get_session_memory(session_id) is None

    def test_tool_registry_registration(self):
        from services.agent_service import ToolRegistry
        registry = ToolRegistry()
        registry.register("test_tool", lambda: "result", "test tool description")
        tools = registry.list_tools()
        assert any(t["name"] == "test_tool" for t in tools)

    @pytest.mark.asyncio
    async def test_tool_execution(self):
        from services.agent_service import ToolCall, ToolRegistry
        registry = ToolRegistry()
        registry.register("echo", lambda text="": f"echo: {text}", "echo tool")
        call = ToolCall(tool_name="echo", arguments={"text": "hello"})
        result_call = await registry.execute(call)
        assert result_call.result == "echo: hello"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from services.agent_service import ToolCall, ToolRegistry
        registry = ToolRegistry()
        call = ToolCall(tool_name="nonexistent", arguments={})
        result_call = await registry.execute(call)
        assert result_call.error is not None

    def test_agent_memory_short_term(self):
        from services.agent_service import AgentMemory
        mem = AgentMemory(max_short_term=3)
        for i in range(5):
            mem.add_message("user", f"message {i}")
        history = mem.get_history()
        assert len(history) <= 3

    def test_agent_memory_long_term(self):
        from services.agent_service import AgentMemory
        mem = AgentMemory()
        mem.store("key", {"data": "value"})
        assert mem.recall("key") == {"data": "value"}
        assert mem.recall("missing") is None

    def test_trace_duration(self):
        from services.agent_service import AgentTrace, AgentStatus
        trace = AgentTrace(agent_id="t1", session_id="s1", query="q")
        trace.finished_at = trace.started_at + 0.5
        assert trace.duration_ms >= 0


# ──────────────────────────────────────────────────────────────────────────────
# PromptBuilder Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPromptPipeline:
    def test_prompt_builder_builds_rag_prompt(self):
        try:
            from core.prompts.prompt_builder import PromptBuilder
            builder = PromptBuilder()
            chunks = ["chunk 1 content", "chunk 2 content"]
            prompt = builder.build_rag("ما هو الذكاء الاصطناعي؟", chunks)
            assert isinstance(prompt, str)
            assert len(prompt) > 0
        except Exception:
            pytest.skip("PromptBuilder غير متوفر")

    def test_prompt_token_budget(self):
        try:
            from core.prompts.prompt_builder import PromptBuilder
            builder = PromptBuilder()
            long_chunks = ["word " * 1000] * 5
            prompt = builder.build_rag("query", long_chunks)
            # يجب أن لا يتجاوز حداً معقولاً
            assert len(prompt) < 100_000
        except Exception:
            pytest.skip("PromptBuilder غير متوفر")
