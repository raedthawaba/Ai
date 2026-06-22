"""
test_model.py — Unit tests for HajeenModel and HajeenForCausalLM.
"""

import os
import tempfile
import pytest
import torch

from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenModel, HajeenForCausalLM


@pytest.fixture
def tiny_config():
    """Minimal config for fast tests."""
    return HajeenConfig(
        vocab_size=256,
        d_model=64,
        n_layers=2,
        n_heads=4,
        d_ff=128,
        max_seq_len=32,
        dropout=0.0,
    )


@pytest.fixture
def tiny_model(tiny_config):
    return HajeenForCausalLM(tiny_config)


class TestHajeenModel:

    def test_forward_shape(self, tiny_config):
        model = HajeenModel(tiny_config)
        batch, seq = 2, 10
        ids = torch.randint(0, tiny_config.vocab_size, (batch, seq))
        out = model(ids)
        assert "last_hidden_state" in out
        assert out["last_hidden_state"].shape == (batch, seq, tiny_config.d_model)

    def test_output_hidden_states(self, tiny_config):
        model = HajeenModel(tiny_config)
        ids = torch.randint(0, tiny_config.vocab_size, (1, 8))
        out = model(ids, output_hidden_states=True)
        assert "hidden_states" in out
        # Should have one hidden state per layer + input embedding
        assert len(out["hidden_states"]) == tiny_config.n_layers + 1

    def test_output_attentions(self, tiny_config):
        model = HajeenModel(tiny_config)
        ids = torch.randint(0, tiny_config.vocab_size, (1, 8))
        out = model(ids, output_attentions=True)
        assert "attentions" in out

    def test_num_parameters(self, tiny_config):
        model = HajeenModel(tiny_config)
        n = model.num_parameters()
        assert n > 0

    def test_no_nan_in_output(self, tiny_config):
        model = HajeenModel(tiny_config)
        ids = torch.randint(0, tiny_config.vocab_size, (2, 16))
        out = model(ids)
        assert not torch.isnan(out["last_hidden_state"]).any()


class TestHajeenForCausalLM:

    def test_forward_logits_shape(self, tiny_config, tiny_model):
        batch, seq = 2, 10
        ids = torch.randint(0, tiny_config.vocab_size, (batch, seq))
        out = tiny_model(ids)
        assert out["logits"].shape == (batch, seq, tiny_config.vocab_size)

    def test_loss_computation(self, tiny_config, tiny_model):
        ids = torch.randint(1, tiny_config.vocab_size, (2, 10))
        out = tiny_model(input_ids=ids, labels=ids)
        assert "loss" in out
        assert out["loss"].item() > 0

    def test_loss_with_ignored_positions(self, tiny_config, tiny_model):
        ids = torch.randint(1, tiny_config.vocab_size, (2, 10))
        labels = ids.clone()
        labels[:, :5] = -100  # ignore first 5 positions
        out = tiny_model(input_ids=ids, labels=labels)
        assert "loss" in out
        assert not torch.isnan(out["loss"])

    def test_num_parameters(self, tiny_model):
        n = tiny_model.num_parameters()
        assert n > 0
        print(f"\n  Tiny model params: {n:,}")

    def test_save_and_load(self, tiny_config, tiny_model):
        tiny_model.eval()
        ids = torch.randint(0, tiny_config.vocab_size, (1, 5))
        with torch.no_grad():
            out_before = tiny_model(ids)["logits"]

        with tempfile.TemporaryDirectory() as d:
            tiny_model.save_pretrained(d)
            assert os.path.exists(os.path.join(d, "model.pt"))
            assert os.path.exists(os.path.join(d, "config.json"))

            loaded = HajeenForCausalLM.from_pretrained(d)
            with torch.no_grad():
                out_after = loaded(ids)["logits"]

        assert torch.allclose(out_before, out_after, atol=1e-5)

    def test_no_nan_logits(self, tiny_config, tiny_model):
        ids = torch.randint(0, tiny_config.vocab_size, (2, 8))
        out = tiny_model(ids)
        assert not torch.isnan(out["logits"]).any()

    def test_repr(self, tiny_model):
        s = repr(tiny_model)
        assert "HajeenForCausalLM" in s

    def test_gradient_flows(self, tiny_config, tiny_model):
        tiny_model.train()
        ids = torch.randint(1, tiny_config.vocab_size, (2, 8))
        out = tiny_model(input_ids=ids, labels=ids)
        out["loss"].backward()
        # At least one parameter should have a gradient
        grads = [p.grad for p in tiny_model.parameters() if p.grad is not None]
        assert len(grads) > 0

    def test_gqa_config(self):
        cfg = HajeenConfig(
            vocab_size=256, d_model=64, n_heads=4, n_kv_heads=2,
            n_layers=2, d_ff=128, max_seq_len=32,
        )
        model = HajeenForCausalLM(cfg)
        ids = torch.randint(0, 256, (1, 8))
        out = model(ids)
        assert out["logits"].shape == (1, 8, 256)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
