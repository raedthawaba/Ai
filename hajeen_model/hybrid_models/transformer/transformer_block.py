"""
transformer_block.py — Single Transformer Decoder Block.

Each block contains:
    1. Pre-norm → Multi-Head Self-Attention → Residual
    2. Pre-norm → Feed-Forward Network → Residual

This is the decoder-only architecture used by all modern auto-regressive LLMs.
"""

from __future__ import annotations

from typing import Optional, Tuple
import torch
import torch.nn as nn

from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.attention.multi_head_attention import MultiHeadAttention
from hajeen_model.layers.feed_forward import FeedForward
from hajeen_model.layers.normalization import build_norm
from hajeen_model.attention.kv_cache import KVCache


class TransformerBlock(nn.Module):
    """
    A single decoder transformer block.

    Architecture (Pre-LN):
        x = x + Attention(RMSNorm(x))
        x = x + FFN(RMSNorm(x))

    Args:
        config: HajeenConfig.
        layer_idx: Index of this block within the full stack (0-indexed).
    """

    def __init__(self, config: HajeenConfig, layer_idx: int) -> None:
        super().__init__()
        self.layer_idx = layer_idx

        # Attention sub-layer
        self.attn_norm = build_norm(config.norm_type, config.d_model, config.norm_eps)
        self.attn = MultiHeadAttention(config, layer_idx=layer_idx)

        # Feed-Forward sub-layer
        self.ff_norm = build_norm(config.norm_type, config.d_model, config.norm_eps)
        self.ff = FeedForward(config)

        self.dropout = nn.Dropout(p=config.dropout)

    def forward(
        self,
        x: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        kv_cache: Optional[KVCache] = None,
        start_pos: int = 0,
        use_causal_mask: bool = True,
        output_attentions: bool = False,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Args:
            x: FloatTensor (batch, seq_len, d_model).
            attention_mask: Optional additive mask.
            kv_cache: Optional KV cache for inference.
            start_pos: Position offset for KV cache.
            use_causal_mask: Whether to apply causal masking.
            output_attentions: Return attention weights if True.

        Returns:
            (hidden_states, attn_weights_or_None)
        """
        # ── Self-Attention with Pre-Norm ─────────────────────────────────
        residual = x
        attn_out, attn_weights = self.attn(
            self.attn_norm(x),
            attention_mask=attention_mask,
            kv_cache=kv_cache,
            start_pos=start_pos,
            use_causal_mask=use_causal_mask,
        )
        x = residual + self.dropout(attn_out)

        # ── Feed-Forward with Pre-Norm ───────────────────────────────────
        residual = x
        ff_out = self.ff(self.ff_norm(x))
        x = residual + self.dropout(ff_out)

        return x, attn_weights if output_attentions else None
