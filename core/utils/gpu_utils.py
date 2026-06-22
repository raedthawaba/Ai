from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GPUUtils:
    """Utilities for GPU detection and memory management."""

    @staticmethod
    def is_cuda_available() -> bool:
        try:
            import torch  # type: ignore
            return torch.cuda.is_available()
        except ImportError:
            return False

    @staticmethod
    def is_mps_available() -> bool:
        try:
            import torch  # type: ignore
            return torch.backends.mps.is_available()
        except (ImportError, AttributeError):
            return False

    @staticmethod
    def gpu_count() -> int:
        try:
            import torch  # type: ignore
            return torch.cuda.device_count()
        except ImportError:
            return 0

    @staticmethod
    def gpu_memory_info(device_idx: int = 0) -> Dict[str, float]:
        try:
            import torch  # type: ignore
            if not torch.cuda.is_available():
                return {}
            props = torch.cuda.get_device_properties(device_idx)
            total = props.total_memory / (1024 ** 3)
            allocated = torch.cuda.memory_allocated(device_idx) / (1024 ** 3)
            reserved = torch.cuda.memory_reserved(device_idx) / (1024 ** 3)
            return {
                "total_gb": round(total, 2),
                "allocated_gb": round(allocated, 2),
                "reserved_gb": round(reserved, 2),
                "free_gb": round(total - reserved, 2),
            }
        except Exception as exc:
            logger.debug("GPU memory info error: %s", exc)
            return {}

    @staticmethod
    def get_device_name(device_idx: int = 0) -> str:
        try:
            import torch  # type: ignore
            return torch.cuda.get_device_name(device_idx)
        except Exception:
            return "unknown"

    @staticmethod
    def empty_cache() -> None:
        try:
            import torch  # type: ignore
            torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def best_device() -> str:
        if GPUUtils.is_cuda_available():
            return "cuda"
        if GPUUtils.is_mps_available():
            return "mps"
        return "cpu"

    @staticmethod
    def summary() -> Dict:
        return {
            "cuda_available": GPUUtils.is_cuda_available(),
            "mps_available": GPUUtils.is_mps_available(),
            "gpu_count": GPUUtils.gpu_count(),
            "best_device": GPUUtils.best_device(),
            "gpu_memory": GPUUtils.gpu_memory_info() if GPUUtils.is_cuda_available() else {},
        }
