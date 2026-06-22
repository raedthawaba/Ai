"""
scaled_dot_product.py — Core attention score computation.

Implements:
    - Scaled dot-product attention (Vaswani et al. 2017)
    - Causal masking (autoregressive decoder)
    - Attention dropout
    - Flash-Attention compatible interface

Formula:
    Attention(Q, K, V) = softmax(QK^T / sqrt(d_k) + mask) · V
"""

from __future__ import annotations

import math
import torch
import torch.nn.functional as F
from typing import Optional


def scaled_dot_product_attention(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    mask: Optional[torch.Tensor] = None,
    dropout_p: float = 0.0,
    is_causal: bool = False,
    scale: Optional[float] = None,
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Compute scaled dot-product attention.

    Args:
        q: Query tensor  (batch, n_heads, seq_q, head_dim).
        k: Key tensor    (batch, n_kv_heads, seq_k, head_dim).
        v: Value tensor  (batch, n_kv_heads, seq_k, head_dim).
        mask: Optional additive mask (broadcast-compatible with (batch, n_heads, seq_q, seq_k)).
              Use -inf to block positions.
        dropout_p: Attention weight dropout probability.
        is_causal: Apply autoregressive causal mask automatically.
        scale: Override 1/sqrt(head_dim). Defaults to 1/sqrt(head_dim).

    Returns:
        output: FloatTensor (batch, n_heads, seq_q, head_dim).
        weights: FloatTensor (batch, n_heads, seq_q, seq_k) — attention probabilities.
    """
    d_k = q.size(-1)
    scale_factor = scale if scale is not None else 1.0 / math.sqrt(d_k)

    # Repeat KV heads for GQA: if n_kv_heads < n_heads, each KV head serves
    # n_heads // n_kv_heads query heads.
    n_heads = q.size(1)
    n_kv_heads = k.size(1)
    if n_kv_heads < n_heads:
        reps = n_heads // n_kv_heads
        k = k.repeat_interleave(reps, dim=1)
        v = v.repeat_interleave(reps, dim=1)

    # Raw attention scores: (batch, n_heads, seq_q, seq_k)
    scores = torch.matmul(q, k.transpose(-2, -1)) * scale_factor

    # Causal mask: upper-triangular positions set to -inf
    if is_causal:
        seq_q, seq_k = q.size(-2), k.size(-2)
        causal_mask = torch.triu(
            torch.ones(seq_q, seq_k, device=q.device, dtype=torch.bool),
            diagonal=1,
        )
        scores = scores.masked_fill(causal_mask, float("-inf"))

    # Optional additional mask (e.g., padding mask)
    if mask is not None:
        scores = scores + mask

    # Softmax + dropout
    weights = F.softmax(scores, dim=-1)
    if dropout_p > 0.0 and torch.is_grad_enabled():
        weights = F.dropout(weights, p=dropout_p)

    # Weighted sum of values
    output = torch.matmul(weights, v)

    return output, weights


def build_causal_mask(seq_len: int, device: torch.device = None) -> torch.Tensor:
    """
    Build a causal (autoregressive) additive mask.

    Returns:
        FloatTensor of shape (1, 1, seq_len, seq_len) with 0.0 on/below
        diagonal and -inf above diagonal.
    """
    mask = torch.triu(
        torch.full((seq_len, seq_len), float("-inf"), device=device),
        diagonal=1,
    )
    return mask.unsqueeze(0).unsqueeze(0)


def build_padding_mask(
    input_ids: torch.Tensor,
    pad_token_id: int = 0,
) -> torch.Tensor:
    """
    Build an additive attention mask from a padding token id.

    Positions where input_ids == pad_token_id get -inf, others get 0.

    Args:
        input_ids: LongTensor (batch, seq_len).
        pad_token_id: Token id used for padding.

    Returns:
        FloatTensor (batch, 1, 1, seq_len) — broadcast-ready mask.
    """
    padding = (input_ids == pad_token_id).float()  # (batch, seq_len)
    mask = padding.unsqueeze(1).unsqueeze(2) * float("-inf")  # (batch,1,1,seq_len)
    mask = mask.nan_to_num(nan=0.0, posinf=0.0, neginf=float("-inf"))
    return mask
