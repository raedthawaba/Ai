"""
Tensor Parallelism — splits model layers across multiple GPUs for large model inference.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.distributed as dist
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class TensorParallelConfig:
    def __init__(self, tensor_parallel_size: int, pipeline_parallel_size: int = 1) -> None:
        self.tensor_parallel_size = tensor_parallel_size
        self.pipeline_parallel_size = pipeline_parallel_size
        self.world_size = tensor_parallel_size * pipeline_parallel_size


class TensorParallelManager:
    """Manages tensor parallelism across multiple GPUs."""

    def __init__(self, config: TensorParallelConfig) -> None:
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not available")

        self.config = config
        self._initialized = False

    def initialize(self, rank: int, master_addr: str = "localhost", master_port: str = "12355") -> None:
        os.environ["MASTER_ADDR"] = master_addr
        os.environ["MASTER_PORT"] = master_port

        dist.init_process_group(
            backend="nccl",
            rank=rank,
            world_size=self.config.world_size,
        )
        torch.cuda.set_device(rank % torch.cuda.device_count())
        self._initialized = True
        logger.info("Tensor parallel initialized: rank=%d/%d", rank, self.config.world_size)

    def split_linear_layer(self, weight: Any, dim: int = 0) -> Any:
        if not self._initialized:
            raise RuntimeError("Not initialized")
        chunk_size = weight.shape[dim] // dist.get_world_size()
        rank = dist.get_rank()
        start = rank * chunk_size
        end = start + chunk_size
        if dim == 0:
            return weight[start:end]
        return weight[:, start:end]

    def all_reduce(self, tensor: Any) -> Any:
        dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
        return tensor

    def all_gather(self, tensor: Any) -> Any:
        tensors = [torch.zeros_like(tensor) for _ in range(dist.get_world_size())]
        dist.all_gather(tensors, tensor)
        return torch.cat(tensors, dim=-1)

    def cleanup(self) -> None:
        if self._initialized and dist.is_initialized():
            dist.destroy_process_group()
            self._initialized = False


class ColumnParallelLinear(torch.nn.Module if TORCH_AVAILABLE else object):
    """Linear layer split across GPUs along output dimension."""

    def __init__(self, in_features: int, out_features: int, tp_manager: TensorParallelManager) -> None:
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not available")
        super().__init__()
        self.tp = tp_manager
        local_out = out_features // tp_manager.config.tensor_parallel_size
        self.linear = torch.nn.Linear(in_features, local_out, bias=False)

    def forward(self, x: Any) -> Any:
        local_out = self.linear(x)
        return self.tp.all_gather(local_out)
