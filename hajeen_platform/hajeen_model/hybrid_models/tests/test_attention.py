"""
test_attention.py — Unit tests for attention mechanisms.
"""

import pytest
import torch
from hajeen_model.attention.scaled_dot_product import (
    scaled_dot_product_attention,
    build_causal_mask,
    build_padding_mask,
)
from hajeen_model.attention.kv_cache import KVCache, KVCacheList
from hajeen_model.attention.multi_head_attention import MultiHeadAttention
from hajeen_model.config.hajeen_config import HajeenConfig


class TestScaledDotProductAttention:

    def test_output_shape(self):
        B, H, S, D = 2, 4, 10, 16
        q = torch.randn(B, H, S, D)
        k = torch.randn(B, H, S, D)
        v = torch.randn(B, H, S, D)
        out, weights = scaled_dot_product_attention(q, k, v)
        assert out.shape == (B, H, S, D)
        assert weights.shape == (B, H, S, S)

    def test_causal_mask_effect(self):
        B, H, S, D = 1, 1, 5, 8
        q = torch.randn(B, H, S, D)
        k = torch.randn(B, H, S, D)
        v = torch.randn(B, H, S, D)
        _, weights = scaled_dot_product_attention(q, k, v, is_causal=True)
        # Upper triangle should be near zero (masked by -inf → softmax → 0)
        upper = torch.triu(weights[0, 0], diagonal=1)
        assert upper.abs().max().item() < 1e-5

    def test_gqa_broadcasting(self):
        B, n_heads, n_kv, S, D = 2, 8, 2, 6, 16
        q = torch.randn(B, n_heads, S, D)
        k = torch.randn(B, n_kv, S, D)
        v = torch.randn(B, n_kv, S, D)
        out, _ = scaled_dot_product_attention(q, k, v)
        assert out.shape == (B, n_heads, S, D)

    def test_no_nan(self):
        B, H, S, D = 2, 4, 8, 32
        q = torch.randn(B, H, S, D)
        k = torch.randn(B, H, S, D)
        v = torch.randn(B, H, S, D)
        out, _ = scaled_dot_product_attention(q, k, v, is_causal=True)
        assert not torch.isnan(out).any()

    def test_build_causal_mask(self):
        mask = build_causal_mask(5)
        assert mask.shape == (1, 1, 5, 5)
        # Diagonal and below should be 0, above should be -inf
        assert mask[0, 0, 0, 0].item() == 0.0
        assert mask[0, 0, 0, 1].item() == float("-inf")


class TestKVCache:

    def test_update_returns_correct_shape(self):
        cache = KVCache(n_kv_heads=2, head_dim=8, max_batch_size=1, max_seq_len=16)
        k = torch.randn(1, 2, 4, 8)
        v = torch.randn(1, 2, 4, 8)
        full_k, full_v = cache.update(k, v, start_pos=0)
        assert full_k.shape == (1, 2, 4, 8)

    def test_update_accumulates(self):
        cache = KVCache(n_kv_heads=2, head_dim=8, max_batch_size=1, max_seq_len=16)
        k1 = torch.randn(1, 2, 4, 8)
        k2 = torch.randn(1, 2, 3, 8)
        cache.update(k1, k1, start_pos=0)
        full_k, _ = cache.update(k2, k2, start_pos=4)
        assert full_k.shape == (1, 2, 7, 8)

    def test_reset(self):
        cache = KVCache(n_kv_heads=2, head_dim=8, max_batch_size=1, max_seq_len=16)
        k = torch.randn(1, 2, 4, 8)
        cache.update(k, k, start_pos=0)
        assert cache.current_length == 4
        cache.reset()
        assert cache.current_length == 0

    def test_overflow_raises(self):
        cache = KVCache(n_kv_heads=2, head_dim=8, max_batch_size=1, max_seq_len=4)
        k = torch.randn(1, 2, 5, 8)
        with pytest.raises(ValueError, match="overflow"):
            cache.update(k, k, start_pos=0)


class TestMultiHeadAttention:

    @pytest.fixture
    def tiny_cfg(self):
        return HajeenConfig(
            vocab_size=256, d_model=64, n_heads=4, n_layers=2,
            d_ff=128, max_seq_len=32,
        )

    def test_output_shape(self, tiny_cfg):
        attn = MultiHeadAttention(tiny_cfg, layer_idx=0)
        x = torch.randn(2, 10, tiny_cfg.d_model)
        out, weights = attn(x)
        assert out.shape == (2, 10, tiny_cfg.d_model)

    def test_no_nan(self, tiny_cfg):
        attn = MultiHeadAttention(tiny_cfg, layer_idx=0)
        x = torch.randn(1, 8, tiny_cfg.d_model)
        out, _ = attn(x)
        assert not torch.isnan(out).any()

    def test_gqa_attention(self):
        cfg = HajeenConfig(
            vocab_size=256, d_model=64, n_heads=4, n_kv_heads=2,
            n_layers=2, d_ff=128, max_seq_len=32,
        )
        attn = MultiHeadAttention(cfg, layer_idx=0)
        x = torch.randn(1, 6, cfg.d_model)
        out, _ = attn(x)
        assert out.shape == (1, 6, cfg.d_model)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
