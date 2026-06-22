"""
rope.py — Rotary Positional Embeddings (RoPE).

Reference: "RoFormer: Enhanced Transformer with Rotary Position Embedding"
           (Su et al., 2021) — https://arxiv.org/abs/2104.09864

RoPE encodes position by rotating query/key vectors in 2D subspaces,
enabling relative position information without adding absolute position
vectors to embeddings.

Key properties:
    - No additional parameters.
    - Generalizes to sequence lengths beyond those seen in training.
    - Used by LLaMA, Mistral, Gemma, Qwen, and most modern LLMs.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from hajeen_model.config.hajeen_config import HajeenConfig


def _build_freqs(
    head_dim: int,
    max_seq_len: int,
    theta: float = 10_000.0,
    device: torch.device = None,
) -> torch.Tensor:
    """
    Build rotary frequency tensor.

    Returns:
        Complex-valued FloatTensor of shape (max_seq_len, head_dim // 2).
    """
    # Frequency bands: θ_i = 1 / (theta ^ (2i / head_dim))
    freqs = 1.0 / (
        theta ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim)
    )
    positions = torch.arange(max_seq_len, device=device).float()
    # outer product: (max_seq_len, head_dim // 2)
    freqs = torch.outer(positions, freqs)
    # Convert to complex representation
    freqs_cis = torch.polar(torch.ones_like(freqs), freqs)
    return freqs_cis


def apply_rotary_emb(
    xq: torch.Tensor,
    xk: torch.Tensor,
    freqs_cis: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Apply rotary embeddings to query and key tensors.

    Args:
        xq: Query tensor of shape (batch, seq_len, n_heads, head_dim).
        xk: Key tensor of shape   (batch, seq_len, n_kv_heads, head_dim).
        freqs_cis: Complex frequency tensor (seq_len, head_dim // 2).

    Returns:
        Rotated (xq, xk) — same shapes as inputs.
    """
    # View real tensors as complex: (..., head_dim) → (..., head_dim // 2) complex
    xq_ = torch.view_as_complex(xq.float().reshape(*xq.shape[:-1], -1, 2))
    xk_ = torch.view_as_complex(xk.float().reshape(*xk.shape[:-1], -1, 2))

    # Broadcast freqs_cis over batch and heads
    # freqs_cis: (seq_len, head_dim // 2)  →  (1, seq_len, 1, head_dim // 2)
    freqs = freqs_cis[: xq_.shape[1]].unsqueeze(0).unsqueeze(2)

    # Element-wise complex multiplication applies rotation
    xq_out = torch.view_as_real(xq_ * freqs).flatten(-2)
    xk_out = torch.view_as_real(xk_ * freqs).flatten(-2)

    return xq_out.type_as(xq), xk_out.type_as(xk)


class RotaryEmbedding(nn.Module):
    """
    Module wrapper for RoPE — caches the frequency tensor.

    Usage:
        rope = RotaryEmbedding(config)
        # Inside attention:
        freqs = rope(seq_len, device)
        xq, xk = apply_rotary_emb(xq, xk, freqs)
    """

    def __init__(self, config: HajeenConfig) -> None:
        super().__init__()
        self.head_dim = config.head_dim
        self.max_seq_len = config.max_seq_len
        self.theta = config.rope_theta

        # Cache frequencies as a non-parameter buffer
        freqs = _build_freqs(self.head_dim, self.max_seq_len, self.theta)
        self.register_buffer("freqs_cis", freqs, persistent=False)

    def forward(self, seq_len: int, device: torch.device = None) -> torch.Tensor:
        """
        Return pre-computed complex frequencies for positions [0, seq_len).

        Args:
            seq_len: Current sequence length.
            device: Target device.

        Returns:
            Complex tensor of shape (seq_len, head_dim // 2).
        """
        if seq_len > self.max_seq_len:
            # Extend cache on-the-fly if needed
            freqs = _build_freqs(self.head_dim, seq_len, self.theta, device=device)
            return freqs
        return self.freqs_cis[:seq_len].to(device=device)
