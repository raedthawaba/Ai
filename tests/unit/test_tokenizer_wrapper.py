"""Tests for TokenizerWrapper — section 5.13."""
from __future__ import annotations
import pytest
from data_engine.processing.transformation.tokenizer_wrapper import (
    TokenizerWrapper, TokenizerConfig,
    count_tokens, truncate_tokens,
    _estimate_tokens_fallback,
)


EN_TEXT = "The quick brown fox jumps over the lazy dog near the riverside."
AR_TEXT = "الذكاء الاصطناعي يُغير العالم بأساليب مبتكرة وتقنيات متطورة جداً."
LONG_TEXT = EN_TEXT * 50


class TestFallbackEstimate:
    def test_empty_returns_zero(self):
        assert _estimate_tokens_fallback("") == 0

    def test_latin_estimate(self):
        tokens = _estimate_tokens_fallback(EN_TEXT, language="en")
        assert tokens > 0

    def test_arabic_estimate(self):
        tokens = _estimate_tokens_fallback(AR_TEXT, language="ar")
        assert tokens > 0

    def test_arabic_denser_than_latin(self):
        # Arabic chars per token = 2 vs 4 → more tokens for same char count
        ar = _estimate_tokens_fallback("ا" * 40, language="ar")
        en = _estimate_tokens_fallback("a" * 40, language="en")
        assert ar >= en


class TestCountTokens:
    def test_basic_count(self):
        n = count_tokens(EN_TEXT)
        assert n > 0

    def test_empty_returns_zero(self):
        assert count_tokens("") == 0

    def test_more_text_more_tokens(self):
        n1 = count_tokens(EN_TEXT)
        n2 = count_tokens(EN_TEXT * 3)
        assert n2 > n1


class TestTruncateTokens:
    def test_short_text_unchanged(self):
        result = truncate_tokens(EN_TEXT, max_tokens=10000)
        assert result == EN_TEXT

    def test_long_text_truncated(self):
        result = truncate_tokens(LONG_TEXT, max_tokens=10)
        assert len(result) < len(LONG_TEXT)
        assert len(result) > 0

    def test_zero_max_returns_empty(self):
        result = truncate_tokens(EN_TEXT, max_tokens=0)
        assert result == ""

    def test_empty_text_returns_empty(self):
        result = truncate_tokens("", max_tokens=100)
        assert result == ""


class TestTokenizerWrapper:
    def setup_method(self):
        self.wrapper = TokenizerWrapper()

    def test_count_tokens_returns_positive(self):
        n = self.wrapper.count_tokens(EN_TEXT)
        assert n > 0

    def test_count_tokens_empty(self):
        assert self.wrapper.count_tokens("") == 0

    def test_truncate_short_text_unchanged(self):
        result = self.wrapper.truncate_tokens(EN_TEXT, max_tokens=10000)
        assert result == EN_TEXT

    def test_truncate_long_text(self):
        result = self.wrapper.truncate_tokens(LONG_TEXT, max_tokens=5)
        assert len(result) < len(LONG_TEXT)
        assert len(result) > 0

    def test_fits_in_context_true(self):
        assert self.wrapper.fits_in_context(EN_TEXT, max_tokens=10000)

    def test_fits_in_context_false(self):
        assert not self.wrapper.fits_in_context(LONG_TEXT, max_tokens=1)

    def test_batch_count(self):
        counts = self.wrapper.batch_count([EN_TEXT, AR_TEXT, ""])
        assert len(counts) == 3
        assert counts[2] == 0

    def test_backend_property_is_string(self):
        assert isinstance(self.wrapper.backend, str)
        assert self.wrapper.backend in ("tiktoken", "fallback")

    def test_arabic_text(self):
        n = self.wrapper.count_tokens(AR_TEXT)
        assert n > 0

    def test_custom_config(self):
        cfg = TokenizerConfig(encoding="cl100k_base", language="ar")
        wrapper = TokenizerWrapper(config=cfg)
        n = wrapper.count_tokens(AR_TEXT)
        assert n > 0
