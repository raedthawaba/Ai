"""
tokenizer_loader.py — Unified tokenizer interface for Hajeen.

Wraps BPETokenizer and optionally SentencePiece with a consistent API.
"""

from __future__ import annotations

import os
from typing import List, Optional, Union

from hajeen_model.tokenizer.bpe_tokenizer import BPETokenizer


class HajeenTokenizer:
    """
    High-level tokenizer loader that wraps BPETokenizer.

    Provides a consistent encode/decode interface regardless of
    the underlying tokenizer backend (BPE or SentencePiece).

    Usage:
        tokenizer = HajeenTokenizer.from_pretrained("tokenizer_model/")
        ids = tokenizer.encode("مرحباً بالعالم")
        text = tokenizer.decode(ids)
    """

    def __init__(self, backend: BPETokenizer) -> None:
        self._backend = backend

    # ── Factory methods ───────────────────────────────────────────────────

    @classmethod
    def from_pretrained(cls, directory: str) -> "HajeenTokenizer":
        """Load a trained tokenizer from a directory."""
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Tokenizer directory not found: {directory}")
        backend = BPETokenizer.load(directory)
        return cls(backend)

    @classmethod
    def train_new(
        cls,
        texts: List[str],
        vocab_size: int = 32_000,
        min_frequency: int = 2,
        save_dir: Optional[str] = None,
    ) -> "HajeenTokenizer":
        """Train a new tokenizer from scratch and optionally save it."""
        backend = BPETokenizer()
        backend.train(texts, vocab_size=vocab_size, min_frequency=min_frequency)
        if save_dir:
            backend.save(save_dir)
        return cls(backend)

    # ── Core API ──────────────────────────────────────────────────────────

    def encode(
        self,
        text: str,
        add_bos: bool = False,
        add_eos: bool = False,
        max_length: Optional[int] = None,
        truncation: bool = False,
        padding: bool = False,
        return_tensors: Optional[str] = None,
    ) -> Union[List[int], "torch.Tensor"]:
        """
        Encode text to token ids.

        Args:
            text: Input string.
            add_bos: Prepend <bos>.
            add_eos: Append <eos>.
            max_length: Maximum sequence length.
            truncation: Truncate if exceeding max_length.
            padding: Pad to max_length with <pad>.
            return_tensors: "pt" for PyTorch tensor, None for list.

        Returns:
            List of ints or a PyTorch LongTensor (shape [1, seq_len]).
        """
        ids = self._backend.encode(text, add_bos=add_bos, add_eos=add_eos)

        if truncation and max_length is not None:
            ids = ids[:max_length]

        if padding and max_length is not None:
            pad = max_length - len(ids)
            if pad > 0:
                ids = ids + [self._backend.pad_token_id] * pad

        if return_tensors == "pt":
            import torch
            return torch.tensor([ids], dtype=torch.long)

        return ids

    def encode_batch(
        self,
        texts: List[str],
        add_bos: bool = False,
        add_eos: bool = False,
        max_length: Optional[int] = None,
        truncation: bool = True,
        padding: bool = True,
        return_tensors: Optional[str] = None,
    ) -> Union[List[List[int]], "torch.Tensor"]:
        """
        Encode a batch of texts with optional padding/truncation.

        Returns:
            List of lists or a PyTorch LongTensor (shape [batch, seq_len]).
        """
        encoded = [
            self.encode(
                t,
                add_bos=add_bos,
                add_eos=add_eos,
                max_length=max_length,
                truncation=truncation,
            )
            for t in texts
        ]

        if padding:
            max_len = max_length or max(len(e) for e in encoded)
            encoded = [
                e + [self._backend.pad_token_id] * (max_len - len(e))
                for e in encoded
            ]

        if return_tensors == "pt":
            import torch
            return torch.tensor(encoded, dtype=torch.long)

        return encoded

    def decode(
        self,
        ids: Union[List[int], "torch.Tensor"],
        skip_special_tokens: bool = True,
    ) -> str:
        """Decode token ids to string."""
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        return self._backend.decode(ids, skip_special_tokens=skip_special_tokens)

    def decode_batch(
        self,
        batch_ids: Union[List[List[int]], "torch.Tensor"],
        skip_special_tokens: bool = True,
    ) -> List[str]:
        """Decode a batch of token id sequences."""
        if hasattr(batch_ids, "tolist"):
            batch_ids = batch_ids.tolist()
        return [self.decode(ids, skip_special_tokens=skip_special_tokens) for ids in batch_ids]

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def vocab_size(self) -> int:
        return self._backend.vocab_size

    @property
    def pad_token_id(self) -> int:
        return self._backend.pad_token_id

    @property
    def bos_token_id(self) -> int:
        return self._backend.bos_token_id

    @property
    def eos_token_id(self) -> int:
        return self._backend.eos_token_id

    @property
    def unk_token_id(self) -> int:
        return self._backend.unk_token_id

    def __len__(self) -> int:
        return self.vocab_size

    def __repr__(self) -> str:
        return f"HajeenTokenizer(vocab_size={self.vocab_size})"
