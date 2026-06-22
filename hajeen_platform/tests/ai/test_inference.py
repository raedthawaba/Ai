"""9.11 — Inference Engine Tests."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncIterator

from core.inference_engine.inference_config import InferenceConfig
from core.inference_engine.sampler import Sampler
from core.inference_engine.stopping import StoppingCriteria
from core.inference_engine.response_parser import ResponseParser
from core.inference_engine.context_manager import ContextManager
from core.inference_engine.batching import BatchInferenceProcessor, BatchRequest


class TestInferenceConfig:
    def test_default_values(self):
        cfg = InferenceConfig()
        assert cfg.max_new_tokens == 512
        assert 0.0 <= cfg.temperature <= 2.0
        assert 0.0 <= cfg.top_p <= 1.0

    def test_greedy_preset(self):
        cfg = InferenceConfig.greedy()
        assert cfg.do_sample is False
        assert cfg.top_k == 0

    def test_creative_preset(self):
        cfg = InferenceConfig.creative()
        assert cfg.temperature > 1.0

    def test_precise_preset(self):
        cfg = InferenceConfig.precise()
        assert cfg.temperature < 0.5


class TestSampler:
    def test_temperature_scaling(self):
        logits = [1.0, 2.0, 3.0]
        scaled = Sampler.temperature_scale(logits, 0.5)
        assert scaled == [2.0, 4.0, 6.0]

    def test_temperature_zero_raises(self):
        with pytest.raises(ValueError):
            Sampler.temperature_scale([1.0], 0.0)

    def test_top_k_filter(self):
        logits = [1.0, 5.0, 3.0, 2.0, 4.0]
        filtered = Sampler.top_k_filter(logits, k=2)
        assert filtered[1] == 5.0
        assert filtered[4] == 4.0
        assert filtered[0] == float("-inf")

    def test_softmax_sums_to_one(self):
        logits = [1.0, 2.0, 3.0]
        probs = Sampler.softmax(logits)
        assert abs(sum(probs) - 1.0) < 1e-6

    def test_greedy_selects_max(self):
        logits = [0.1, 0.9, 0.3]
        idx = Sampler.greedy(logits)
        assert idx == 1

    def test_top_p_filter(self):
        logits = [5.0, 3.0, 1.0, 0.5, 0.1]
        filtered = Sampler.top_p_filter(logits, p=0.9)
        assert filtered[0] == 5.0

    def test_repetition_penalty(self):
        logits = [1.0, 2.0, 3.0]
        penalized = Sampler.repetition_penalty_apply(logits, [0, 1], penalty=1.5)
        assert penalized[0] < logits[0]
        assert penalized[2] == logits[2]


class TestStoppingCriteria:
    def test_stop_on_max_tokens(self):
        sc = StoppingCriteria(max_tokens=3)
        assert not sc.should_stop_on_token(1)
        assert not sc.should_stop_on_token(2)
        assert sc.should_stop_on_token(3)

    def test_stop_on_sequence(self):
        sc = StoppingCriteria(stop_sequences=["END", "STOP"])
        assert sc.should_stop_on_text("Hello world END here")
        assert not sc.should_stop_on_text("Hello world")

    def test_truncate_at_stop(self):
        sc = StoppingCriteria(stop_sequences=["###"])
        result = sc.truncate_at_stop("Hello world ### more text")
        assert result == "Hello world "

    def test_eos_token_stops(self):
        sc = StoppingCriteria(eos_token_id=2)
        assert not sc.should_stop_on_token(1)
        assert sc.should_stop_on_token(2)

    def test_reset(self):
        sc = StoppingCriteria(max_tokens=2)
        sc.should_stop_on_token(1)
        sc.should_stop_on_token(2)
        sc.reset()
        assert sc.tokens_generated == 0


class TestResponseParser:
    def test_clean_removes_stop_sequences(self):
        text = "Hello world END more stuff"
        cleaned = ResponseParser.clean(text, stop_sequences=["END"])
        assert "END" not in cleaned
        assert "Hello world" in cleaned

    def test_extract_code_blocks(self):
        text = "Here is code:\n```python\nprint('hello')\n```"
        blocks = ResponseParser.extract_code_blocks(text)
        assert len(blocks) == 1
        assert "print" in blocks[0]

    def test_extract_json(self):
        text = '{"key": "value", "num": 42}'
        result = ResponseParser.extract_json(text)
        assert result is not None
        assert result["key"] == "value"

    def test_extract_json_from_block(self):
        text = '```json\n{"status": "ok"}\n```'
        result = ResponseParser.extract_json(text)
        assert result is not None
        assert result["status"] == "ok"

    def test_extract_list(self):
        text = "- Item one\n- Item two\n• Item three"
        items = ResponseParser.extract_list(text)
        assert len(items) >= 2

    def test_to_structured(self):
        result = ResponseParser.to_structured("Hello there", model_id="test-model")
        assert result["text"] == "Hello there"
        assert result["model"] == "test-model"


class TestContextManager:
    def test_estimate_tokens(self):
        cm = ContextManager(max_context_tokens=4096)
        messages = [{"role": "user", "content": "Hello world how are you?"}]
        tokens = cm.estimate_tokens(messages)
        assert tokens > 0

    def test_available_context(self):
        cm = ContextManager(max_context_tokens=4096, reserve_tokens=512)
        assert cm.available_context == 3584

    def test_fit_text_no_truncation(self):
        cm = ContextManager(max_context_tokens=4096)
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = list(range(10))
        mock_tokenizer.decode.return_value = "short text"
        result = cm.fit_text("short text", mock_tokenizer, max_tokens=100)
        assert result == "short text"
