from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GPUNode:
    node_id: str
    total_memory_gb: float
    available_memory_gb: float
    gpu_count: int
    gpu_type: str = "unknown"
    status: str = "healthy"
    utilisation_pct: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def is_healthy(self) -> bool:
        return self.status == "healthy"

    def memory_free_pct(self) -> float:
        if self.total_memory_gb == 0:
            return 0.0
        return self.available_memory_gb / self.total_memory_gb


@dataclass
class TaskRequest:
    task_id: str
    required_memory_gb: float
    required_gpus: int = 1
    priority: int = 1
    gpu_type_preference: Optional[str] = None


class DistributedGPUScheduler:
    """
    Intelligent GPU scheduler for multi-node, multi-GPU environments.
    Supports:
    - First-fit and best-fit placement strategies
    - Priority-based scheduling
    - Node health monitoring
    - GPU type affinity
    - Load balancing
    """

    def __init__(self, strategy: str = "best_fit") -> None:
        self._nodes: Dict[str, GPUNode] = {}
        self._allocations: Dict[str, str] = {}  # task_id -> node_id
        self._strategy = strategy
        logger.info("DistributedGPUScheduler initialised (strategy=%s).", strategy)

    # ── Node Management ───────────────────────────────────────────────────

    def register_node(self, node: GPUNode) -> None:
        self._nodes[node.node_id] = node
        logger.info(
            "GPU node '%s' registered — %d GPUs, %.1f GB VRAM (%s).",
            node.node_id, node.gpu_count, node.total_memory_gb, node.gpu_type,
        )

    def update_node(
        self,
        node_id: str,
        available_memory_gb: float,
        utilisation_pct: float = 0.0,
        status: str = "healthy",
    ) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].available_memory_gb = available_memory_gb
            self._nodes[node_id].utilisation_pct = utilisation_pct
            self._nodes[node_id].status = status
            self._nodes[node_id].last_updated = time.time()

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        logger.info("GPU node '%s' removed from scheduler.", node_id)

    # ── Scheduling ────────────────────────────────────────────────────────

    def schedule(self, request: TaskRequest) -> Optional[str]:
        """
        Find the best node for the given task request.
        Returns node_id or None if no suitable node exists.
        """
        candidates = [
            node for node in self._nodes.values()
            if node.is_healthy()
            and node.available_memory_gb >= request.required_memory_gb
            and node.gpu_count >= request.required_gpus
        ]

        # Apply GPU type preference filter if specified
        if request.gpu_type_preference:
            preferred = [n for n in candidates if n.gpu_type == request.gpu_type_preference]
            if preferred:
                candidates = preferred

        if not candidates:
            logger.warning(
                "No suitable GPU node for task '%s' (%.1f GB, %d GPU).",
                request.task_id, request.required_memory_gb, request.required_gpus,
            )
            return None

        # Apply placement strategy
        if self._strategy == "best_fit":
            selected = min(candidates, key=lambda n: n.available_memory_gb)
        elif self._strategy == "least_loaded":
            selected = min(candidates, key=lambda n: n.utilisation_pct)
        elif self._strategy == "most_free":
            selected = max(candidates, key=lambda n: n.available_memory_gb)
        else:  # first_fit
            selected = candidates[0]

        # Reserve memory
        selected.available_memory_gb -= request.required_memory_gb
        self._allocations[request.task_id] = selected.node_id
        logger.info(
            "Task '%s' scheduled on node '%s' (remaining: %.1f GB).",
            request.task_id, selected.node_id, selected.available_memory_gb,
        )
        return selected.node_id

    def release(self, task_id: str, freed_memory_gb: float) -> None:
        """Release GPU resources allocated to a completed task."""
        node_id = self._allocations.pop(task_id, None)
        if node_id and node_id in self._nodes:
            self._nodes[node_id].available_memory_gb += freed_memory_gb
            logger.info(
                "Task '%s' released %.1f GB on node '%s'.",
                task_id, freed_memory_gb, node_id,
            )

    # ── Status ────────────────────────────────────────────────────────────

    def cluster_summary(self) -> Dict[str, Any]:
        healthy = [n for n in self._nodes.values() if n.is_healthy()]
        total_mem = sum(n.total_memory_gb for n in self._nodes.values())
        avail_mem = sum(n.available_memory_gb for n in healthy)
        return {
            "total_nodes": len(self._nodes),
            "healthy_nodes": len(healthy),
            "total_gpus": sum(n.gpu_count for n in self._nodes.values()),
            "total_memory_gb": round(total_mem, 2),
            "available_memory_gb": round(avail_mem, 2),
            "active_allocations": len(self._allocations),
        }

    def get_node(self, node_id: str) -> Optional[GPUNode]:
        return self._nodes.get(node_id)


class ParallelExecutionEngine:
    """
    Manages tensor parallelism and pipeline parallelism configuration
    for distributed model inference and training.
    """

    def __init__(
        self,
        world_size: int,
        tensor_parallel_size: int,
        pipeline_parallel_size: int,
    ) -> None:
        self.world_size = world_size
        self.tp_size = tensor_parallel_size
        self.pp_size = pipeline_parallel_size

        expected = tensor_parallel_size * pipeline_parallel_size
        if world_size != expected:
            logger.warning(
                "world_size=%d ≠ TP(%d) × PP(%d)=%d — ensure your config is correct.",
                world_size, tensor_parallel_size, pipeline_parallel_size, expected,
            )

    def get_parallel_config(self) -> Dict[str, int]:
        return {
            "world_size": self.world_size,
            "tensor_parallel_size": self.tp_size,
            "pipeline_parallel_size": self.pp_size,
            "data_parallel_size": self.world_size // (self.tp_size * self.pp_size),
        }

    def setup_distributed_groups(self, backend: str = "nccl") -> bool:
        """
        Initialise PyTorch distributed process groups.
        Must be called once per process before using distributed ops.
        """
        try:
            import torch.distributed as dist
            if dist.is_initialized():
                logger.info("Distributed groups already initialised.")
                return True
            import os
            if "MASTER_ADDR" not in os.environ:
                os.environ.setdefault("MASTER_ADDR", "localhost")
                os.environ.setdefault("MASTER_PORT", "29500")
                os.environ.setdefault("RANK", "0")
                os.environ.setdefault("WORLD_SIZE", str(self.world_size))
            dist.init_process_group(backend=backend)
            logger.info("Distributed process group initialised (backend=%s).", backend)
            return True
        except Exception as exc:
            logger.error("Failed to init distributed groups: %s", exc)
            return False

    def get_rank(self) -> int:
        try:
            import torch.distributed as dist
            return dist.get_rank() if dist.is_initialized() else 0
        except Exception:
            return 0

    def get_world_size(self) -> int:
        try:
            import torch.distributed as dist
            return dist.get_world_size() if dist.is_initialized() else 1
        except Exception:
            return 1
