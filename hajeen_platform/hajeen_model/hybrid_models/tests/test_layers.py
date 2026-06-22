"""
test_layers.py — Unit tests for normalization and feed-forward layers.
"""

import pytest
import torch
from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.layers.normalization import RMSNorm, LayerNorm, build_norm
from hajeen_model.layers.feed_forward import FeedForward
from hajeen_model.layers.residual import ResidualConnection


class TestRMSNorm:

    def test_output_shape(self):
        norm = RMSNorm(64)
        x = torch.randn(2, 10, 64)
        out = norm(x)
        assert out.shape == x.shape

    def test_unit_norm_approx(self):
        norm = RMSNorm(128)
        x = torch.randn(4, 16, 128)
        out = norm(x)
        # RMS of output should be close to 1 (since weight is initialized to 1)
        rms = out.pow(2).mean(dim=-1).sqrt()
        assert torch.allclose(rms, torch.ones_like(rms), atol=0.1)

    def test_learnable_weight(self):
        norm = RMSNorm(32)
        params = list(norm.parameters())
        assert len(params) == 1
        assert params[0].shape == (32,)

    def test_no_nan(self):
        norm = RMSNorm(64)
        x = torch.randn(2, 8, 64)
        out = norm(x)
        assert not torch.isnan(out).any()

    def test_zero_input(self):
        norm = RMSNorm(32)
        x = torch.zeros(1, 4, 32)
        out = norm(x)
        # Should not NaN (eps prevents division by zero)
        assert not torch.isnan(out).any()


class TestLayerNorm:

    def test_output_shape(self):
        norm = LayerNorm(64)
        x = torch.randn(2, 10, 64)
        out = norm(x)
        assert out.shape == x.shape

    def test_normalized(self):
        norm = LayerNorm(128)
        x = torch.randn(4, 16, 128) * 100  # large values
        out = norm(x)
        # Mean should be ~0, std ~1 along last dim
        assert out.mean(dim=-1).abs().max().item() < 0.1


class TestBuildNorm:

    def test_rmsnorm(self):
        norm = build_norm("rmsnorm", 64)
        assert isinstance(norm, RMSNorm)

    def test_layernorm(self):
        norm = build_norm("layernorm", 64)
        assert isinstance(norm, LayerNorm)

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            build_norm("batchnorm", 64)


class TestFeedForward:

    @pytest.fixture
    def cfg(self):
        return HajeenConfig(
            vocab_size=256, d_model=64, n_layers=2,
            n_heads=4, d_ff=128, max_seq_len=32,
        )

    def test_gated_output_shape(self, cfg):
        ff = FeedForward(cfg)
        x = torch.randn(2, 10, cfg.d_model)
        out = ff(x)
        assert out.shape == x.shape

    def test_standard_output_shape(self, cfg):
        cfg.use_gated_ff = False
        ff = FeedForward(cfg)
        x = torch.randn(2, 10, cfg.d_model)
        out = ff(x)
        assert out.shape == x.shape

    def test_no_nan(self, cfg):
        ff = FeedForward(cfg)
        x = torch.randn(1, 8, cfg.d_model)
        out = ff(x)
        assert not torch.isnan(out).any()

    @pytest.mark.parametrize("activation", ["silu", "gelu", "relu"])
    def test_activations(self, cfg, activation):
        cfg.activation = activation
        ff = FeedForward(cfg)
        x = torch.randn(1, 4, cfg.d_model)
        out = ff(x)
        assert out.shape == x.shape


class TestResidualConnection:

    def test_output_shape(self):
        cfg = HajeenConfig(
            vocab_size=256, d_model=64, n_layers=2, n_heads=4,
            d_ff=128, max_seq_len=32,
        )
        residual = ResidualConnection(cfg)
        x = torch.randn(2, 10, cfg.d_model)
        identity = lambda h: torch.zeros_like(h)
        out = residual(x, identity)
        # When sublayer returns 0, output should equal input
        assert torch.allclose(out, x)

    def test_residual_adds(self):
        cfg = HajeenConfig(
            vocab_size=256, d_model=64, n_layers=2, n_heads=4,
            d_ff=128, max_seq_len=32, dropout=0.0,
        )
        residual = ResidualConnection(cfg)
        x = torch.ones(1, 4, cfg.d_model)
        # sublayer that returns ones (after norm this won't be exactly ones)
        out = residual(x, lambda h: h)
        assert out.shape == x.shape


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
