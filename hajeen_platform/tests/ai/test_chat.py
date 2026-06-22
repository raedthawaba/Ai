"""9.11 — Chat & Memory Service Tests."""
from __future__ import annotations

import pytest
import time
from unittest.mock import MagicMock

from core.memory.short_term_memory import ShortTermMemory
from core.memory.long_term_memory import LongTermMemory
from core.memory.memory_manager import MemoryManager
from core.prompts.prompt_builder import PromptBuilder
from core.prompts.templates import TemplateRegistry
from core.prompts.system_prompts import SystemPromptLibrary
from core.prompts.conversation_formatter import (
    ConversationFormatter, Message, MessageRole
)
from services.moderation_service import ModerationService


class TestShortTermMemory:
    def test_add_and_get(self):
        mem = ShortTermMemory(max_turns=10)
        mem.add("sess1", "user", "Hello")
        mem.add("sess1", "assistant", "Hi there")
        entries = mem.get("sess1")
        assert len(entries) == 2
        assert entries[0].role == "user"

    def test_max_turns_eviction(self):
        mem = ShortTermMemory(max_turns=2)
        for i in range(5):
            mem.add("s1", "user", f"msg {i}")
        entries = mem.get("s1")
        assert len(entries) <= 4

    def test_get_as_messages(self):
        mem = ShortTermMemory()
        mem.add("s1", "user", "Hello")
        msgs = mem.get_as_messages("s1")
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello"

    def test_clear(self):
        mem = ShortTermMemory()
        mem.add("s1", "user", "test")
        mem.clear("s1")
        assert mem.get("s1") == []

    def test_multiple_sessions(self):
        mem = ShortTermMemory()
        mem.add("s1", "user", "Hello from 1")
        mem.add("s2", "user", "Hello from 2")
        assert mem.turn_count("s1") == 1
        assert mem.turn_count("s2") == 1


class TestLongTermMemory:
    def setup_method(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.mem = LongTermMemory(storage_dir=self.tmpdir)

    def test_save_and_load(self):
        self.mem.save("session1", "user_pref", {"theme": "dark"})
        result = self.mem.load("session1", "user_pref")
        assert result == {"theme": "dark"}

    def test_load_missing_returns_default(self):
        result = self.mem.load("no-session", "no-key", default="fallback")
        assert result == "fallback"

    def test_delete(self):
        self.mem.save("s1", "key", "value")
        assert self.mem.delete("s1", "key") is True
        assert self.mem.load("s1", "key") is None

    def test_list_keys(self):
        self.mem.save("s1", "k1", "v1")
        self.mem.save("s1", "k2", "v2")
        keys = self.mem.list_keys("s1")
        assert "k1" in keys
        assert "k2" in keys


class TestPromptBuilder:
    def test_build_chat(self):
        builder = PromptBuilder(model_format="chatml")
        prompt = builder.build_chat("Hello, how are you?")
        assert "Hello" in prompt
        assert len(prompt) > 10

    def test_build_rag(self):
        builder = PromptBuilder()
        chunks = ["Python is a language.", "It was created by Guido."]
        prompt = builder.build_rag("Who created Python?", chunks)
        assert "Python" in prompt
        assert "Guido" in prompt

    def test_build_completion(self):
        builder = PromptBuilder()
        prompt = builder.build_completion("Once upon a time")
        assert "Once upon a time" in prompt

    def test_build_from_template(self):
        builder = PromptBuilder()
        result = builder.build_from_template("summarize", text="This is a long text to summarize.")
        assert "summarize" in result.lower() or "text" in result.lower()


class TestTemplateRegistry:
    def test_get_existing(self):
        template = TemplateRegistry.get("rag_answer")
        assert template is not None
        assert "context" in template.variables

    def test_get_missing_returns_none(self):
        assert TemplateRegistry.get("nonexistent_template") is None

    def test_render(self):
        template = TemplateRegistry.get_or_raise("summarize")
        result = template.render(text="test content")
        assert "test content" in result

    def test_list_templates(self):
        templates = TemplateRegistry.list_templates()
        assert "rag_answer" in templates
        assert "chat" in templates


class TestSystemPromptLibrary:
    def test_get_default(self):
        prompt = SystemPromptLibrary.get("default")
        assert len(prompt) > 20

    def test_get_missing_returns_default(self):
        prompt = SystemPromptLibrary.get("nonexistent_persona")
        default = SystemPromptLibrary.get("default")
        assert prompt == default

    def test_register_and_get(self):
        SystemPromptLibrary.register("test_persona", "Test system prompt content.")
        assert SystemPromptLibrary.get("test_persona") == "Test system prompt content."

    def test_arabic_prompt_available(self):
        arabic = SystemPromptLibrary.get("arabic")
        assert len(arabic) > 10


class TestConversationFormatter:
    def test_to_chatml(self):
        messages = [
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi"),
        ]
        result = ConversationFormatter.to_chatml(messages)
        assert "<|im_start|>" in result
        assert "Hello" in result

    def test_to_mistral(self):
        messages = [Message(role=MessageRole.USER, content="Explain AI")]
        result = ConversationFormatter.to_mistral(messages)
        assert "[INST]" in result

    def test_trim_history(self):
        messages = [Message(role=MessageRole.USER, content=f"msg {i}") for i in range(30)]
        trimmed = ConversationFormatter.trim_history(messages, max_messages=10)
        assert len(trimmed) <= 10

    def test_to_openai_format(self):
        messages = [Message(role=MessageRole.USER, content="Hello")]
        result = ConversationFormatter.to_openai_messages(messages)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"


class TestModerationService:
    def test_allows_normal_text(self):
        svc = ModerationService()
        result = svc.check("What is machine learning?")
        assert result.action == "allow"
        assert not result.flagged

    def test_blocks_harmful_content(self):
        svc = ModerationService(block_harmful=True)
        result = svc.check("how to make a bomb step by step")
        assert result.action in ("block", "warn")
        assert result.flagged

    def test_blocks_long_input(self):
        svc = ModerationService(max_input_length=100)
        result = svc.check("x" * 200)
        assert result.action == "block"

    def test_is_allowed(self):
        svc = ModerationService()
        assert svc.is_allowed("Tell me about Python")

    def test_filter_output(self):
        svc = ModerationService()
        clean = svc.filter_output("Normal response text.")
        assert clean == "Normal response text."
