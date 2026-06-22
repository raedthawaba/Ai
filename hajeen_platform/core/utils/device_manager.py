from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .gpu_utils import GPUUtils

logger = logging.getLogger(__name__)


class DeviceManager:
    """Determine and manage the compute device for AI workloads."""

    def __init__(self, preferred_device: str = "auto") -> None:
        self._preferred = preferred_device
        self._resolved: Optional[str] = None

    @property
    def device(self) -> str:
        if self._resolved is None:
            self._resolved = self._resolve()
        return self._resolved

    def _resolve(self) -> str:
        pref = self._preferred.lower()
        if pref == "auto":
            device = GPUUtils.best_device()
            logger.info("DeviceManager auto-selected device: %s", device)
            return device
        if pref == "cuda":
            if not GPUUtils.is_cuda_available():
                logger.warning("CUDA requested but not available. Falling back to CPU.")
                return "cpu"
            return "cuda"
        if pref == "mps":
            if not GPUUtils.is_mps_available():
                logger.warning("MPS requested but not available. Falling back to CPU.")
                return "cpu"
            return "mps"
        return "cpu"

    def to_torch_device(self) -> Any:
        try:
            import torch  # type: ignore
            return torch.device(self.device)
        except ImportError as exc:
            raise RuntimeError("PyTorch not installed") from exc

    def get_torch_dtype(self, dtype: str = "float16") -> Any:
        try:
            import torch  # type: ignore
            mapping = {
                "float32": torch.float32,
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "int8": torch.int8,
            }
            return mapping.get(dtype, torch.float16)
        except ImportError as exc:
            raise RuntimeError("PyTorch not installed") from exc

    def info(self) -> dict:
        info: dict = {"device": self.device, "preferred": self._preferred}
        if self.device == "cuda":
            info["gpu_name"] = GPUUtils.get_device_name()
            info["gpu_memory"] = GPUUtils.gpu_memory_info()
        return info
