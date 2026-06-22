"""
HajeenConfig — Central configuration for the Hajeen Foundation Model.

Supports scaling from 100M to multi-billion parameters by adjusting
n_layers, n_heads, d_model, and d_ff.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class HajeenConfig:
    """
    Configuration class for all Hajeen model variants.

    Naming follows modern LLM conventions:
        d_model   — hidden dimension (embedding size)
        n_layers  — number of transformer blocks
        n_heads   — number of attention heads
        n_kv_heads — number of key/value heads (GQA support)
        d_ff      — feedforward inner dimension
        vocab_size — tokenizer vocabulary size
        max_seq_len — maximum sequence length
    """

    # ── Model identity ──────────────────────────────────────────────────────
    model_name: str = "hajeen-base"
    model_version: str = "1.0.0"

    # ── Architecture ────────────────────────────────────────────────────────
    vocab_size: int = 32_000
    d_model: int = 512
    n_layers: int = 6
    n_heads: int = 8
    n_kv_heads: Optional[int] = None          # None → same as n_heads (MHA)
    d_ff: int = 2048                          # feedforward inner dimension
    max_seq_len: int = 2048

    # ── Regularization ──────────────────────────────────────────────────────
    dropout: float = 0.0
    attention_dropout: float = 0.0

    # ── Normalization ───────────────────────────────────────────────────────
    norm_type: str = "rmsnorm"                # "rmsnorm" | "layernorm"
    norm_eps: float = 1e-5

    # ── Positional encoding ─────────────────────────────────────────────────
    pos_encoding: str = "rope"                # "rope" | "learned" | "sinusoidal"
    rope_theta: float = 10_000.0              # RoPE frequency base

    # ── Activation ──────────────────────────────────────────────────────────
    activation: str = "silu"                  # "silu" | "gelu" | "relu"
    use_gated_ff: bool = True                  # SwiGLU-style gated feedforward

    # ── Tokenizer ───────────────────────────────────────────────────────────
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2
    unk_token_id: int = 3

    # ── Initialization ──────────────────────────────────────────────────────
    initializer_range: float = 0.02

    # ── Dtype ───────────────────────────────────────────────────────────────
    torch_dtype: str = "float32"              # "float32" | "float16" | "bfloat16"

    # ── Pre-defined scale presets ────────────────────────────────────────────
    # Use HajeenConfig.from_preset("1B") for convenience.

    # ── Extra metadata ───────────────────────────────────────────────────────
    extra: dict = field(default_factory=dict)

    # ── Derived properties ───────────────────────────────────────────────────
    @property
    def head_dim(self) -> int:
        """Dimension of each attention head."""
        assert self.d_model % self.n_heads == 0, (
            f"d_model ({self.d_model}) must be divisible by n_heads ({self.n_heads})"
        )
        return self.d_model // self.n_heads

    @property
    def effective_kv_heads(self) -> int:
        """Actual number of KV heads (GQA when < n_heads)."""
        return self.n_kv_heads if self.n_kv_heads is not None else self.n_heads

    def validate(self) -> None:
        """Raise ValueError for any invalid configuration."""
        if self.d_model % self.n_heads != 0:
            raise ValueError(
                f"d_model ({self.d_model}) must be divisible by n_heads ({self.n_heads})"
            )
        if self.n_kv_heads is not None and self.n_heads % self.n_kv_heads != 0:
            raise ValueError(
                f"n_heads ({self.n_heads}) must be divisible by n_kv_heads ({self.n_kv_heads})"
            )
        if self.norm_type not in ("rmsnorm", "layernorm"):
            raise ValueError(f"Unknown norm_type: {self.norm_type}")
        if self.pos_encoding not in ("rope", "learned", "sinusoidal"):
            raise ValueError(f"Unknown pos_encoding: {self.pos_encoding}")
        if self.activation not in ("silu", "gelu", "relu"):
            raise ValueError(f"Unknown activation: {self.activation}")

    # ── Serialization ────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "HajeenConfig":
        known = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, path: str) -> "HajeenConfig":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)

    # ── Scale presets ────────────────────────────────────────────────────────
    @classmethod
    def from_preset(cls, preset: str) -> "HajeenConfig":
        """
        Create a config from a named preset.

        Available presets:
            "100M"  — 100 million parameters
            "300M"  — 300 million parameters
            "1B"    — 1 billion parameters
            "3B"    — 3 billion parameters
            "7B"    — 7 billion parameters
            "13B"   — 13 billion parameters
            "70B"   — 70 billion parameters
        """
        presets = {
            "100M": dict(
                model_name="hajeen-100m",
                d_model=512, n_layers=12, n_heads=8,
                d_ff=2048, max_seq_len=2048,
            ),
            "300M": dict(
                model_name="hajeen-300m",
                d_model=1024, n_layers=16, n_heads=16,
                d_ff=4096, max_seq_len=2048,
            ),
            "1B": dict(
                model_name="hajeen-1b",
                d_model=2048, n_layers=24, n_heads=16,
                n_kv_heads=8, d_ff=5632, max_seq_len=4096,
            ),
            "3B": dict(
                model_name="hajeen-3b",
                d_model=3072, n_layers=32, n_heads=24,
                n_kv_heads=8, d_ff=8192, max_seq_len=4096,
            ),
            "7B": dict(
                model_name="hajeen-7b",
                d_model=4096, n_layers=32, n_heads=32,
                n_kv_heads=8, d_ff=11008, max_seq_len=4096,
            ),
            "13B": dict(
                model_name="hajeen-13b",
                d_model=5120, n_layers=40, n_heads=40,
                n_kv_heads=8, d_ff=13824, max_seq_len=4096,
            ),
            "70B": dict(
                model_name="hajeen-70b",
                d_model=8192, n_layers=80, n_heads=64,
                n_kv_heads=8, d_ff=28672, max_seq_len=4096,
            ),
        }
        if preset not in presets:
            raise ValueError(f"Unknown preset '{preset}'. Choose from: {list(presets)}")
        cfg = cls()
        for k, v in presets[preset].items():
            setattr(cfg, k, v)
        cfg.validate()
        return cfg

    def __repr__(self) -> str:
        return (
            f"HajeenConfig("
            f"name={self.model_name!r}, "
            f"d_model={self.d_model}, "
            f"n_layers={self.n_layers}, "
            f"n_heads={self.n_heads}, "
            f"vocab_size={self.vocab_size}, "
            f"max_seq_len={self.max_seq_len})"
        )
