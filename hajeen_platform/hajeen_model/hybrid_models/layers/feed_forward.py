"""
feed_forward.py — Feed-Forward Network (FFN) layers.

Supports:
    - Standard FFN: Linear → Activation → Linear
    - Gated FFN (SwiGLU): (Linear(x) * SiLU(Gate(x))) → Linear
      Used by LLaMA, Mistral, and most modern LLMs.

The gated variant doubles the number of linear projections but
empirically outperforms standard FFN with same parameter count.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from hajeen_model.config.hajeen_config import HajeenConfig


class FeedForward(nn.Module):
    """
    Position-wise Feed-Forward Network.

    Gated variant (use_gated_ff=True, recommended):
        output = down_proj(silu(gate_proj(x)) * up_proj(x))

    Standard variant (use_gated_ff=False):
        output = down_proj(act(up_proj(x)))

    Args:
        config: HajeenConfig instance.
    """

    def __init__(self, config: HajeenConfig) -> None:
        super().__init__()
        self.d_model = config.d_model
        self.d_ff = config.d_ff
        self.use_gated = config.use_gated_ff
        self.activation = config.activation
        self.dropout = nn.Dropout(p=config.dropout)

        if self.use_gated:
            # SwiGLU: two up-projections (gate and value)
            self.gate_proj = nn.Linear(config.d_model, config.d_ff, bias=False)
            self.up_proj   = nn.Linear(config.d_model, config.d_ff, bias=False)
            self.down_proj = nn.Linear(config.d_ff, config.d_model, bias=False)
        else:
            self.up_proj   = nn.Linear(config.d_model, config.d_ff, bias=False)
            self.down_proj = nn.Linear(config.d_ff, config.d_model, bias=False)
            self.gate_proj = None

        self._init_weights(config.initializer_range)

    def _init_weights(self, std: float) -> None:
        for layer in [self.gate_proj, self.up_proj, self.down_proj]:
            if layer is not None:
                nn.init.normal_(layer.weight, std=std)

    def _activate(self, x: torch.Tensor) -> torch.Tensor:
        if self.activation == "silu":
            return F.silu(x)
        elif self.activation == "gelu":
            return F.gelu(x, approximate="tanh")
        elif self.activation == "relu":
            return F.relu(x)
        else:
            raise ValueError(f"Unknown activation: {self.activation}")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: FloatTensor (batch, seq_len, d_model).

        Returns:
            FloatTensor (batch, seq_len, d_model).
        """
        if self.use_gated:
            # SwiGLU gate mechanism
            gate = self._activate(self.gate_proj(x))
            up   = self.up_proj(x)
            hidden = gate * up
        else:
            hidden = self._activate(self.up_proj(x))

        return self.dropout(self.down_proj(hidden))
