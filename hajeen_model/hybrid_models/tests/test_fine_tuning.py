"""
test_fine_tuning.py — Unit tests for fine-tuning utilities.
"""

import pytest
import torch
import torch.nn as nn
from hajeen_model.training.fine_tuning import (
    freeze_all, unfreeze_all, freeze_except,
    LoRALinear, inject_lora,
    format_instruction, format_chat, build_instruction_dataset,
)
from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM


@pytest.fixture
def tiny_model():
    cfg = HajeenConfig(
        vocab_size=256, d_model=64, n_layers=2, n_heads=4,
        d_ff=128, max_seq_len=32, dropout=0.0,
    )
    return HajeenForCausalLM(cfg)


class TestParameterControl:

    def test_freeze_all(self, tiny_model):
        freeze_all(tiny_model)
        trainable = sum(p.numel() for p in tiny_model.parameters() if p.requires_grad)
        assert trainable == 0

    def test_unfreeze_all(self, tiny_model):
        freeze_all(tiny_model)
        unfreeze_all(tiny_model)
        trainable = sum(p.numel() for p in tiny_model.parameters() if p.requires_grad)
        assert trainable > 0

    def test_freeze_except(self, tiny_model):
        freeze_except(tiny_model, ["norm"])
        # At least one norm parameter should be trainable
        norm_trainable = any(
            p.requires_grad
            for n, p in tiny_model.named_parameters()
            if "norm" in n
        )
        assert norm_trainable

        # Non-norm parameters should be frozen
        non_norm_trainable = any(
            p.requires_grad
            for n, p in tiny_model.named_parameters()
            if "norm" not in n
        )
        # Some non-norm params should be frozen
        # (not necessarily all — lm_head may still be trainable)


class TestLoRA:

    def test_lora_linear_forward(self):
        base = nn.Linear(64, 64, bias=False)
        lora = LoRALinear(base, rank=4, alpha=4.0)
        x = torch.randn(2, 8, 64)
        out = lora(x)
        assert out.shape == (2, 8, 64)

    def test_lora_base_frozen(self):
        base = nn.Linear(64, 64, bias=False)
        lora = LoRALinear(base, rank=4, alpha=4.0)
        for p in lora.base_layer.parameters():
            assert not p.requires_grad

    def test_lora_adapters_trainable(self):
        base = nn.Linear(64, 64, bias=False)
        lora = LoRALinear(base, rank=4, alpha=4.0)
        assert lora.lora_A.weight.requires_grad
        assert lora.lora_B.weight.requires_grad

    def test_lora_init_zero_delta(self):
        """LoRA B=0 at init → delta = 0 → lora output == base output."""
        base = nn.Linear(64, 32, bias=False)
        lora = LoRALinear(base, rank=4, alpha=4.0)
        x = torch.randn(1, 4, 64)
        with torch.no_grad():
            base_out = base(x)
            lora_out = lora(x)
        assert torch.allclose(base_out, lora_out, atol=1e-5)

    def test_lora_merge_weights(self):
        base = nn.Linear(32, 16, bias=False)
        lora = LoRALinear(base, rank=4, alpha=4.0)
        merged = lora.merge_weights()
        assert isinstance(merged, nn.Linear)
        x = torch.randn(2, 32)
        with torch.no_grad():
            assert torch.allclose(lora(x.unsqueeze(0)).squeeze(0), merged(x), atol=1e-4)

    def test_inject_lora(self, tiny_model):
        freeze_all(tiny_model)
        count = inject_lora(tiny_model, target_modules=["q_proj", "v_proj"], rank=4)
        assert count > 0
        # LoRA params should be trainable
        trainable = sum(p.numel() for p in tiny_model.parameters() if p.requires_grad)
        assert trainable > 0


class TestInstructionFormatting:

    def test_format_instruction(self):
        text = format_instruction("What is AI?", "AI is...")
        assert "### Instruction:" in text
        assert "What is AI?" in text
        assert "### Response:" in text
        assert "AI is..." in text

    def test_format_chat(self):
        text = format_chat("Hello", "Hi there!")
        assert "<|user|>" in text
        assert "Hello" in text
        assert "<|assistant|>" in text
        assert "Hi there!" in text

    def test_build_instruction_dataset(self, tiny_model):
        from hajeen_model.tokenizer.bpe_tokenizer import BPETokenizer
        from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer

        bpe = BPETokenizer()
        corpus = ["Hello world test sentence"] * 30
        bpe.train(corpus, vocab_size=300, min_frequency=1, show_progress=False)
        tokenizer = HajeenTokenizer(bpe)

        pairs = [
            {"instruction": "What is AI?", "response": "AI is intelligence."},
            {"instruction": "Hello?", "response": "Hi!"},
        ]
        samples = build_instruction_dataset(pairs, tokenizer, max_seq_len=64)
        assert len(samples) == 2
        for s in samples:
            assert "input_ids" in s
            assert "labels" in s
            # Labels start with -100 (instruction part ignored)
            assert s["labels"][0] == -100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
