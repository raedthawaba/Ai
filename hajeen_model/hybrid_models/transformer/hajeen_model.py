"""
hajeen_model.py — Core HajeenModel and HajeenForCausalLM.

HajeenModel:
    - Token embeddings
    - Optional positional embeddings (when not using RoPE)
    - Stack of TransformerBlocks
    - Final normalization

HajeenForCausalLM:
    - HajeenModel backbone
    - LM head (linear projection to vocab)
    - Loss computation (cross-entropy)
    - save/load utilities
"""

from __future__ import annotations

import os
import math
from typing import Dict, List, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.embeddings.token_embeddings import TokenEmbeddings
from hajeen_model.embeddings.position_embeddings import SinusoidalEmbeddings, LearnedEmbeddings
from hajeen_model.transformer.transformer_block import TransformerBlock
from hajeen_model.layers.normalization import build_norm
from hajeen_model.attention.kv_cache import KVCacheList


class HajeenModel(nn.Module):
    """
    Core transformer backbone (no LM head).

    Outputs:
        hidden_states: FloatTensor (batch, seq_len, d_model).
        all_hidden_states (optional): tuple of per-layer hidden states.
        all_attentions (optional): tuple of per-layer attention weights.
    """

    def __init__(self, config: HajeenConfig) -> None:
        super().__init__()
        config.validate()
        self.config = config

        # ── Token Embeddings ─────────────────────────────────────────────
        self.embed_tokens = TokenEmbeddings(config, scale_embeddings=False)

        # ── Positional Embeddings (skip for RoPE — handled inside attention) ──
        if config.pos_encoding == "sinusoidal":
            self.pos_emb = SinusoidalEmbeddings(config)
        elif config.pos_encoding == "learned":
            self.pos_emb = LearnedEmbeddings(config)
        else:
            self.pos_emb = None  # RoPE applied inside each attention block

        # ── Transformer Blocks ───────────────────────────────────────────
        self.layers = nn.ModuleList(
            [TransformerBlock(config, layer_idx=i) for i in range(config.n_layers)]
        )

        # ── Final Normalization ──────────────────────────────────────────
        self.norm = build_norm(config.norm_type, config.d_model, config.norm_eps)

        self.dropout = nn.Dropout(p=config.dropout)

        # Initialize weights
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, std=self.config.initializer_range)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, std=self.config.initializer_range)

    def get_input_embeddings(self) -> nn.Embedding:
        return self.embed_tokens.embedding

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        kv_cache_list: Optional[KVCacheList] = None,
        start_pos: int = 0,
        output_hidden_states: bool = False,
        output_attentions: bool = False,
    ) -> Dict[str, torch.Tensor]:
        """
        Args:
            input_ids: LongTensor (batch, seq_len).
            attention_mask: Optional additive mask.
            kv_cache_list: Optional KV cache for incremental decoding.
            start_pos: Position offset (for KV cache).
            output_hidden_states: Include all per-layer hidden states.
            output_attentions: Include all per-layer attention weights.

        Returns:
            dict with keys:
                "last_hidden_state" — (batch, seq_len, d_model)
                "hidden_states" — tuple of tensors (if output_hidden_states)
                "attentions" — tuple of tensors (if output_attentions)
        """
        # Embed tokens
        x = self.embed_tokens(input_ids)

        # Add positional embeddings (for non-RoPE variants)
        if self.pos_emb is not None:
            x = self.pos_emb(x)

        x = self.dropout(x)

        all_hidden = (x,) if output_hidden_states else None
        all_attn = () if output_attentions else None

        # Run through transformer blocks
        for i, layer in enumerate(self.layers):
            cache = kv_cache_list[i] if kv_cache_list is not None else None
            x, attn_w = layer(
                x,
                attention_mask=attention_mask,
                kv_cache=cache,
                start_pos=start_pos,
                use_causal_mask=True,
                output_attentions=output_attentions,
            )
            if output_hidden_states:
                all_hidden = all_hidden + (x,)
            if output_attentions and attn_w is not None:
                all_attn = all_attn + (attn_w,)

        x = self.norm(x)

        out = {"last_hidden_state": x}
        if output_hidden_states:
            out["hidden_states"] = all_hidden
        if output_attentions:
            out["attentions"] = all_attn

        return out

    def num_parameters(self, trainable_only: bool = False) -> int:
        """Return total (or trainable) parameter count."""
        params = (p for p in self.parameters() if p.requires_grad) if trainable_only else self.parameters()
        return sum(p.numel() for p in params)


class HajeenForCausalLM(nn.Module):
    """
    Hajeen Language Model for causal (autoregressive) text generation.

    = HajeenModel backbone + LM head (linear → vocab logits)

    The LM head weight is optionally tied to the token embedding matrix
    (weight tying) to reduce parameter count and improve generalization.
    """

    def __init__(self, config: HajeenConfig, tie_weights: bool = True) -> None:
        super().__init__()
        self.config = config
        self.model = HajeenModel(config)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        if tie_weights:
            self.lm_head.weight = self.model.embed_tokens.embedding.weight

    def get_input_embeddings(self) -> nn.Embedding:
        return self.model.get_input_embeddings()

    def forward(
        self,
        input_ids: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        kv_cache_list: Optional[KVCacheList] = None,
        start_pos: int = 0,
        output_hidden_states: bool = False,
        output_attentions: bool = False,
    ) -> Dict[str, torch.Tensor]:
        """
        Args:
            input_ids: LongTensor (batch, seq_len).
            labels: Optional LongTensor (batch, seq_len) for loss computation.
                    Positions with -100 are ignored (standard convention).
            attention_mask: Optional additive mask.
            kv_cache_list: Optional KV cache.
            start_pos: Position offset for KV cache.
            output_hidden_states: Include per-layer hidden states.
            output_attentions: Include per-layer attention weights.

        Returns:
            dict with keys:
                "logits" — (batch, seq_len, vocab_size)
                "loss" — scalar (only if labels provided)
                "hidden_states", "attentions" — optional
        """
        backbone_out = self.model(
            input_ids,
            attention_mask=attention_mask,
            kv_cache_list=kv_cache_list,
            start_pos=start_pos,
            output_hidden_states=output_hidden_states,
            output_attentions=output_attentions,
        )

        hidden = backbone_out["last_hidden_state"]
        logits = self.lm_head(hidden)  # (batch, seq_len, vocab_size)

        out: Dict[str, torch.Tensor] = {"logits": logits}
        if "hidden_states" in backbone_out:
            out["hidden_states"] = backbone_out["hidden_states"]
        if "attentions" in backbone_out:
            out["attentions"] = backbone_out["attentions"]

        # ── Loss ─────────────────────────────────────────────────────────
        if labels is not None:
            # Shift: predict token t+1 from token t
            shift_logits = logits[:, :-1, :].contiguous()
            shift_labels = labels[:, 1:].contiguous()

            loss = F.cross_entropy(
                shift_logits.view(-1, self.config.vocab_size),
                shift_labels.view(-1),
                ignore_index=-100,
            )
            out["loss"] = loss

        return out

    # ── Parameter count ───────────────────────────────────────────────────
    def num_parameters(self, trainable_only: bool = False) -> int:
        params = (p for p in self.parameters() if p.requires_grad) if trainable_only else self.parameters()
        return sum(p.numel() for p in params)

    def __repr__(self) -> str:
        n = self.num_parameters()
        suffix = "B" if n >= 1e9 else "M" if n >= 1e6 else "K"
        scale = 1e9 if n >= 1e9 else 1e6 if n >= 1e6 else 1e3
        return (
            f"HajeenForCausalLM("
            f"params={n/scale:.2f}{suffix}, "
            f"config={self.config})"
        )

    # ── Save / Load ───────────────────────────────────────────────────────
    def save_pretrained(self, directory: str) -> None:
        """
        Save model weights and config to directory.

        Creates:
            directory/config.json
            directory/model.pt
        """
        os.makedirs(directory, exist_ok=True)
        self.config.to_json(os.path.join(directory, "config.json"))
        torch.save(self.state_dict(), os.path.join(directory, "model.pt"))
        print(f"[HajeenForCausalLM] Saved to {directory}/")

    @classmethod
    def from_pretrained(
        cls,
        directory: str,
        map_location: Union[str, torch.device] = "cpu",
        tie_weights: bool = True,
    ) -> "HajeenForCausalLM":
        """
        Load model from a directory created by save_pretrained().

        Args:
            directory: Path to saved model directory.
            map_location: Device to load onto.
            tie_weights: Whether to tie LM head and embedding weights.

        Returns:
            HajeenForCausalLM in eval mode.
        """
        config = HajeenConfig.from_json(os.path.join(directory, "config.json"))
        model = cls(config, tie_weights=tie_weights)
        state = torch.load(
            os.path.join(directory, "model.pt"),
            map_location=map_location,
            weights_only=True,
        )
        model.load_state_dict(state)
        model.eval()
        print(f"[HajeenForCausalLM] Loaded from {directory}/")
        return model
