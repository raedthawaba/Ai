"""
multi_head_attention.py — Multi-Head (and Grouped-Query) Attention.

Supports:
    - Standard Multi-Head Attention (MHA): n_kv_heads == n_heads
    - Grouped-Query Attention (GQA): n_kv_heads < n_heads
    - KV caching for autoregressive inference
    - RoPE positional encoding
    - Causal masking

Reference:
    "Attention Is All You Need" (Vaswani et al., 2017)
    "GQA: Training Generalized Multi-Query Transformer Models" (Ainslie et al., 2023)
"""

from __future__ import annotations

from typing import Optional, Tuple
import torch
import torch.nn as nn

from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.attention.scaled_dot_product import scaled_dot_product_attention
from hajeen_model.attention.kv_cache import KVCache
from hajeen_model.embeddings.rope import RotaryEmbedding, apply_rotary_emb


class MultiHeadAttention(nn.Module):
    """
    Multi-Head Self-Attention with optional Grouped-Query Attention (GQA).

    Projects input hidden states to Q, K, V, computes attention, then
    projects back to d_model.

    Args:
        config: HajeenConfig.
        layer_idx: Layer index (used for logging/debugging only).
    """

    def __init__(self, config: HajeenConfig, layer_idx: int = 0) -> None:
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.effective_kv_heads
        self.head_dim = config.head_dim
        self.d_model = config.d_model
        self.attention_dropout = config.attention_dropout
        self.layer_idx = layer_idx

        # Query projection: d_model → n_heads * head_dim
        self.q_proj = nn.Linear(config.d_model, config.n_heads * config.head_dim, bias=False)
        # Key/Value projections: d_model → n_kv_heads * head_dim
        self.k_proj = nn.Linear(config.d_model, self.n_kv_heads * config.head_dim, bias=False)
        self.v_proj = nn.Linear(config.d_model, self.n_kv_heads * config.head_dim, bias=False)
        # Output projection
        self.o_proj = nn.Linear(config.n_heads * config.head_dim, config.d_model, bias=False)

        # RoPE (only when pos_encoding == "rope")
        self.use_rope = config.pos_encoding == "rope"
        if self.use_rope:
            self.rotary_emb = RotaryEmbedding(config)

        self._init_weights(config.initializer_range)

    def _init_weights(self, std: float) -> None:
        for proj in (self.q_proj, self.k_proj, self.v_proj, self.o_proj):
            nn.init.normal_(proj.weight, std=std)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        kv_cache: Optional[KVCache] = None,
        start_pos: int = 0,
        use_causal_mask: bool = True,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            hidden_states: FloatTensor (batch, seq_len, d_model).
            attention_mask: Optional additive mask (batch, 1, seq_q, seq_k).
            kv_cache: Optional KVCache for incremental decoding.
            start_pos: Starting position for KV cache.
            use_causal_mask: Apply causal mask (True for decoder).

        Returns:
            output: FloatTensor (batch, seq_len, d_model).
            attn_weights: FloatTensor (batch, n_heads, seq_q, seq_k).
        """
        batch, seq_len, _ = hidden_states.shape

        # ── Project Q, K, V ──────────────────────────────────────────────
        q = self.q_proj(hidden_states)  # (B, T, n_heads * head_dim)
        k = self.k_proj(hidden_states)  # (B, T, n_kv_heads * head_dim)
        v = self.v_proj(hidden_states)  # (B, T, n_kv_heads * head_dim)

        # Reshape to (B, n_heads, T, head_dim)
        q = q.view(batch, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch, seq_len, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch, seq_len, self.n_kv_heads, self.head_dim).transpose(1, 2)

        # Transpose back for RoPE: (B, T, n_heads, head_dim)
        if self.use_rope:
            q = q.transpose(1, 2)
            k = k.transpose(1, 2)
            freqs_cis = self.rotary_emb(start_pos + seq_len, device=q.device)
            # Slice to [start_pos : start_pos + seq_len]
            freqs_cis = freqs_cis[start_pos: start_pos + seq_len]
            q, k = apply_rotary_emb(q, k, freqs_cis)
            q = q.transpose(1, 2)
            k = k.transpose(1, 2)

        # ── KV Cache update ──────────────────────────────────────────────
        if kv_cache is not None:
            k, v = kv_cache.update(k, v, start_pos)

        # ── Attention ────────────────────────────────────────────────────
        output, attn_weights = scaled_dot_product_attention(
            q, k, v,
            mask=attention_mask,
            dropout_p=self.attention_dropout if self.training else 0.0,
            is_causal=use_causal_mask and kv_cache is None,
        )

        # ── Output projection ────────────────────────────────────────────
        # Reshape: (B, n_heads, T, head_dim) → (B, T, d_model)
        output = output.transpose(1, 2).contiguous().view(batch, seq_len, self.d_model)
        output = self.o_proj(output)

        return output, attn_weights
