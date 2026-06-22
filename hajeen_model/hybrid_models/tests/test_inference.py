"""
test_inference.py — Unit tests for the Hajeen inference engine.
"""

import pytest
import torch
from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
from hajeen_model.tokenizer.bpe_tokenizer import BPETokenizer
from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer
from hajeen_model.inference.inference_engine import InferenceEngine, GenerationConfig


CORPUS = [
    "Hello world this is a test sentence.",
    "مرحباً هذا اختبار للنموذج اللغوي.",
    "def main(): print('Hello Hajeen')",
    "The quick brown fox jumps over the lazy dog.",
    "الذكاء الاصطناعي والتعلم الآلي.",
] * 30


@pytest.fixture(scope="module")
def tiny_engine():
    # Train a tiny tokenizer
    bpe = BPETokenizer()
    bpe.train(CORPUS, vocab_size=512, min_frequency=1, show_progress=False)
    tokenizer = HajeenTokenizer(bpe)

    # Build a tiny model
    cfg = HajeenConfig(
        vocab_size=bpe.vocab_size,
        d_model=64, n_layers=2, n_heads=4,
        d_ff=128, max_seq_len=64,
        dropout=0.0,
    )
    model = HajeenForCausalLM(cfg)
    engine = InferenceEngine(model, tokenizer, device="cpu")
    return engine


class TestGenerationConfig:

    def test_defaults(self):
        cfg = GenerationConfig()
        assert cfg.do_sample is True
        assert cfg.temperature == 1.0
        assert cfg.top_k == 0
        assert cfg.top_p == 1.0
        assert cfg.max_new_tokens == 256


class TestInferenceEngine:

    def test_greedy_generate(self, tiny_engine):
        cfg = GenerationConfig(do_sample=False, max_new_tokens=5)
        text = tiny_engine.generate("Hello", cfg)
        assert isinstance(text, str)

    def test_sampling_generate(self, tiny_engine):
        cfg = GenerationConfig(
            do_sample=True, temperature=0.8, top_k=10, max_new_tokens=5
        )
        text = tiny_engine.generate("Hello", cfg)
        assert isinstance(text, str)

    def test_nucleus_sampling(self, tiny_engine):
        cfg = GenerationConfig(
            do_sample=True, top_p=0.9, max_new_tokens=5
        )
        text = tiny_engine.generate("Test", cfg)
        assert isinstance(text, str)

    def test_streaming(self, tiny_engine):
        cfg = GenerationConfig(do_sample=False, max_new_tokens=5)
        chunks = list(tiny_engine.stream("Hello", cfg))
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)

    def test_generate_arabic(self, tiny_engine):
        cfg = GenerationConfig(do_sample=False, max_new_tokens=3)
        text = tiny_engine.generate("مرحبا", cfg)
        assert isinstance(text, str)

    def test_max_new_tokens_respected(self, tiny_engine):
        max_tokens = 4
        cfg = GenerationConfig(do_sample=False, max_new_tokens=max_tokens)
        chunks = list(tiny_engine.stream("Hello", cfg))
        # Can't generate more than max_new_tokens
        assert len(chunks) <= max_tokens

    def test_batch_generate(self, tiny_engine):
        cfg = GenerationConfig(do_sample=False, max_new_tokens=3)
        prompts = ["Hello", "مرحبا"]
        results = tiny_engine.generate_batch(prompts, cfg)
        assert len(results) == 2
        assert all(isinstance(r, str) for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
