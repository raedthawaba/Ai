"""
residual.py — Residual (skip) connection with pre-norm support.

Pre-norm (apply norm before sublayer) is standard in modern LLMs and
provides more stable training than post-norm.

Usage:
    residual = ResidualConnection(config)
    x = residual(x, sublayer_fn)
"""

from __future__ import annotations

from typing import Callable
import torch
import torch.nn as nn

from hajeen_model.layers.normalization import build_norm
from hajeen_model.config.hajeen_config import HajeenConfig


class ResidualConnection(nn.Module):
    """
    Pre-norm residual connection:
        output = x + sublayer(norm(x))

    Args:
        config: HajeenConfig.
    """

    def __init__(self, config: HajeenConfig) -> None:
        super().__init__()
        self.norm = build_norm(config.norm_type, config.d_model, config.norm_eps)
        self.dropout = nn.Dropout(p=config.dropout)

    def forward(
        self,
        x: torch.Tensor,
        sublayer: Callable[[torch.Tensor], torch.Tensor],
    ) -> torch.Tensor:
        """
        Args:
            x: Input FloatTensor (batch, seq_len, d_model).
            sublayer: A callable that maps (batch, seq_len, d_model) →
                      (batch, seq_len, d_model).

        Returns:
            FloatTensor (batch, seq_len, d_model).
        """
        return x + self.dropout(sublayer(self.norm(x)))
