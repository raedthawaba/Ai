"""
token_embeddings.py — Token embedding layer for Hajeen.

Maps integer token ids → dense float vectors of dimension d_model.
Includes optional embedding scaling (GPT-NeoX style).
"""

from __future__ import annotations

import math
import torch
import torch.nn as nn
from hajeen_model.config.hajeen_config import HajeenConfig


class TokenEmbeddings(nn.Module):
    """
    Learned token embedding table.

    Shape: (vocab_size, d_model)

    Features:
        - Xavier/normal initialization controlled by config.
        - Optional embedding scaling by sqrt(d_model).
        - Dropout regularization.
        - Weight-tying support (share weights with LM head).

    Args:
        config: HajeenConfig instance.
        scale_embeddings: Multiply embeddings by sqrt(d_model) before dropout.
    """

    def __init__(self, config: HajeenConfig, scale_embeddings: bool = False) -> None:
        super().__init__()
        self.vocab_size = config.vocab_size
        self.d_model = config.d_model
        self.scale_embeddings = scale_embeddings
        self.pad_token_id = config.pad_token_id

        self.embedding = nn.Embedding(
            num_embeddings=config.vocab_size,
            embedding_dim=config.d_model,
            padding_idx=config.pad_token_id,
        )
        self.dropout = nn.Dropout(p=config.dropout)

        self._init_weights(config.initializer_range)

    def _init_weights(self, std: float) -> None:
        nn.init.normal_(self.embedding.weight, mean=0.0, std=std)
        # Zero out the padding embedding
        with torch.no_grad():
            self.embedding.weight[self.pad_token_id].zero_()

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        """
        Args:
            input_ids: LongTensor of shape (batch, seq_len).

        Returns:
            FloatTensor of shape (batch, seq_len, d_model).
        """
        x = self.embedding(input_ids)
        if self.scale_embeddings:
            x = x * math.sqrt(self.d_model)
        return self.dropout(x)

    def get_weight(self) -> torch.Tensor:
        """Return embedding weight matrix (for weight tying with LM head)."""
        return self.embedding.weight
