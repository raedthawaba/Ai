"""
normalization.py — RMSNorm and LayerNorm implementations.

RMSNorm is preferred in modern LLMs (LLaMA, Mistral, etc.) because:
    - No mean-centering step → fewer operations.
    - Empirically matches LayerNorm performance.

LayerNorm is provided for completeness and ablation studies.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class RMSNorm(nn.Module):
    """
    Root Mean Square Layer Normalization.

    RMSNorm(x) = x / RMS(x) * weight
    where RMS(x) = sqrt(mean(x²) + eps)

    Args:
        d_model: Hidden dimension.
        eps: Small constant for numerical stability.
    """

    def __init__(self, d_model: int, eps: float = 1e-5) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(d_model))

    def _norm(self, x: torch.Tensor) -> torch.Tensor:
        rms = x.pow(2).mean(dim=-1, keepdim=True).add(self.eps).sqrt()
        return x / rms

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: FloatTensor (..., d_model).

        Returns:
            Normalized FloatTensor (..., d_model).
        """
        # Cast to float32 for norm, then back to input dtype
        output = self._norm(x.float()).type_as(x)
        return output * self.weight


class LayerNorm(nn.Module):
    """
    Standard Layer Normalization (Ba et al., 2016).

    LayerNorm(x) = (x - mean(x)) / std(x) * weight + bias

    Args:
        d_model: Hidden dimension.
        eps: Numerical stability constant.
        bias: Whether to include learnable bias term.
    """

    def __init__(self, d_model: int, eps: float = 1e-5, bias: bool = True) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(d_model))
        self.bias = nn.Parameter(torch.zeros(d_model)) if bias else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: FloatTensor (..., d_model).

        Returns:
            Normalized FloatTensor (..., d_model).
        """
        return nn.functional.layer_norm(
            x, (x.size(-1),), self.weight, self.bias, self.eps
        )


def build_norm(norm_type: str, d_model: int, eps: float = 1e-5) -> nn.Module:
    """
    Factory function to build a normalization layer by name.

    Args:
        norm_type: "rmsnorm" or "layernorm".
        d_model: Hidden dimension.
        eps: Numerical stability constant.

    Returns:
        nn.Module normalization layer.
    """
    if norm_type == "rmsnorm":
        return RMSNorm(d_model, eps=eps)
    elif norm_type == "layernorm":
        return LayerNorm(d_model, eps=eps)
    else:
        raise ValueError(f"Unknown norm_type: {norm_type!r}. Use 'rmsnorm' or 'layernorm'.")
