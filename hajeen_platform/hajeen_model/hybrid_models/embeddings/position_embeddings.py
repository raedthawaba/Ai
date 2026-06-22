"""
position_embeddings.py — Sinusoidal and learned positional embeddings.

RoPE (Rotary Position Embeddings) lives in rope.py.
"""

from __future__ import annotations

import math
import torch
import torch.nn as nn
from hajeen_model.config.hajeen_config import HajeenConfig


class SinusoidalEmbeddings(nn.Module):
    """
    Fixed sinusoidal positional embeddings (Vaswani et al. 2017).

    PE(pos, 2i)   = sin(pos / 10000^(2i/d_model))
    PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))

    Not learnable; no parameters.
    """

    def __init__(self, config: HajeenConfig) -> None:
        super().__init__()
        self.d_model = config.d_model
        self.max_seq_len = config.max_seq_len

        # Pre-compute and register as buffer (not a parameter)
        pe = self._build_table(config.max_seq_len, config.d_model)
        self.register_buffer("pe", pe, persistent=False)

    @staticmethod
    def _build_table(max_seq_len: int, d_model: int) -> torch.Tensor:
        position = torch.arange(max_seq_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float)
            * -(math.log(10_000.0) / d_model)
        )
        pe = torch.zeros(max_seq_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        return pe.unsqueeze(0)  # (1, max_seq_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Add positional encoding to embeddings.

        Args:
            x: FloatTensor (batch, seq_len, d_model).

        Returns:
            FloatTensor (batch, seq_len, d_model) with positions added.
        """
        seq_len = x.size(1)
        return x + self.pe[:, :seq_len, :]


class LearnedEmbeddings(nn.Module):
    """
    Fully learnable positional embeddings.

    One vector per position, all learned during training.
    Max positions = config.max_seq_len.
    """

    def __init__(self, config: HajeenConfig) -> None:
        super().__init__()
        self.d_model = config.d_model
        self.max_seq_len = config.max_seq_len

        self.embedding = nn.Embedding(config.max_seq_len, config.d_model)
        self.dropout = nn.Dropout(p=config.dropout)
        nn.init.normal_(self.embedding.weight, std=config.initializer_range)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: FloatTensor (batch, seq_len, d_model).

        Returns:
            FloatTensor (batch, seq_len, d_model).
        """
        seq_len = x.size(1)
        positions = torch.arange(seq_len, device=x.device).unsqueeze(0)
        pos_emb = self.embedding(positions)
        return self.dropout(x + pos_emb)
