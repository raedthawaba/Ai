"""
kv_cache.py — Key-Value cache for efficient autoregressive inference.

During inference, instead of recomputing all previous K and V tensors
at every step, we store them and only compute K/V for the new token.

This reduces the per-step complexity from O(n²) to O(n).
"""

from __future__ import annotations

from typing import Optional, Tuple
import torch


class KVCache:
    """
    Key-Value cache for a single transformer layer.

    Grows dynamically as tokens are generated.
    Must be reset between independent generation requests.

    Args:
        n_kv_heads: Number of KV attention heads.
        head_dim: Dimension per head.
        max_batch_size: Maximum batch size for pre-allocation.
        max_seq_len: Maximum sequence length.
        dtype: Cache tensor dtype.
        device: Target device.
    """

    def __init__(
        self,
        n_kv_heads: int,
        head_dim: int,
        max_batch_size: int = 1,
        max_seq_len: int = 2048,
        dtype: torch.dtype = torch.float32,
        device: Optional[torch.device] = None,
    ) -> None:
        self.n_kv_heads = n_kv_heads
        self.head_dim = head_dim
        self.max_seq_len = max_seq_len

        # Pre-allocate cache tensors: (batch, n_kv_heads, max_seq_len, head_dim)
        self.cache_k = torch.zeros(
            max_batch_size, n_kv_heads, max_seq_len, head_dim,
            dtype=dtype, device=device,
        )
        self.cache_v = torch.zeros(
            max_batch_size, n_kv_heads, max_seq_len, head_dim,
            dtype=dtype, device=device,
        )
        self._cur_len = 0

    @property
    def current_length(self) -> int:
        """Number of tokens currently stored in the cache."""
        return self._cur_len

    def update(
        self,
        k: torch.Tensor,
        v: torch.Tensor,
        start_pos: int,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Write new K/V slices and return the full accumulated K/V.

        Args:
            k: Key tensor   (batch, n_kv_heads, seq_len, head_dim).
            v: Value tensor (batch, n_kv_heads, seq_len, head_dim).
            start_pos: Token position offset (0 for first call, grows each step).

        Returns:
            (full_k, full_v) — tensors spanning [0, start_pos + seq_len).
        """
        seq_len = k.size(2)
        end_pos = start_pos + seq_len

        if end_pos > self.max_seq_len:
            raise ValueError(
                f"KV cache overflow: start_pos={start_pos}, seq_len={seq_len}, "
                f"max_seq_len={self.max_seq_len}"
            )

        self.cache_k[:k.size(0), :, start_pos:end_pos, :] = k
        self.cache_v[:v.size(0), :, start_pos:end_pos, :] = v
        self._cur_len = end_pos

        return (
            self.cache_k[:k.size(0), :, :end_pos, :],
            self.cache_v[:v.size(0), :, :end_pos, :],
        )

    def reset(self) -> None:
        """Clear the cache (call between generation requests)."""
        self.cache_k.zero_()
        self.cache_v.zero_()
        self._cur_len = 0

    def to(self, device: torch.device) -> "KVCache":
        self.cache_k = self.cache_k.to(device)
        self.cache_v = self.cache_v.to(device)
        return self


class KVCacheList:
    """
    Manages one KVCache per transformer layer.

    Usage:
        cache = KVCacheList.build(config, max_batch_size=1, device=device)
        # In each layer:
        full_k, full_v = cache[layer_idx].update(k, v, start_pos)
    """

    def __init__(self, caches: list) -> None:
        self._caches = caches

    def __getitem__(self, idx: int) -> KVCache:
        return self._caches[idx]

    def __len__(self) -> int:
        return len(self._caches)

    def reset(self) -> None:
        for c in self._caches:
            c.reset()

    @classmethod
    def build(
        cls,
        config,
        max_batch_size: int = 1,
        device: Optional[torch.device] = None,
        dtype: torch.dtype = torch.float32,
    ) -> "KVCacheList":
        from hajeen_model.config.hajeen_config import HajeenConfig
        caches = [
            KVCache(
                n_kv_heads=config.effective_kv_heads,
                head_dim=config.head_dim,
                max_batch_size=max_batch_size,
                max_seq_len=config.max_seq_len,
                dtype=dtype,
                device=device,
            )
            for _ in range(config.n_layers)
        ]
        return cls(caches)
