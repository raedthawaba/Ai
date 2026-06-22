from __future__ import annotations

import time
from typing import Dict, List, Optional


class GPUMonitor:
    """Monitor GPU utilization and memory usage over time."""

    def __init__(self, sample_interval: float = 5.0) -> None:
        self.sample_interval = sample_interval
        self._samples: List[Dict] = []
        self._max_samples = 1000

    def sample(self) -> Dict:
        snapshot = self._capture_snapshot()
        if len(self._samples) >= self._max_samples:
            self._samples = self._samples[-self._max_samples // 2:]
        self._samples.append(snapshot)
        return snapshot

    def _capture_snapshot(self) -> Dict:
        snapshot: Dict = {"timestamp": time.time(), "gpus": []}
        try:
            import torch  # type: ignore
            if not torch.cuda.is_available():
                snapshot["available"] = False
                return snapshot
            snapshot["available"] = True
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                allocated = torch.cuda.memory_allocated(i)
                reserved = torch.cuda.memory_reserved(i)
                total = props.total_memory
                snapshot["gpus"].append(
                    {
                        "device": i,
                        "name": props.name,
                        "total_gb": round(total / 1024 ** 3, 2),
                        "allocated_gb": round(allocated / 1024 ** 3, 2),
                        "reserved_gb": round(reserved / 1024 ** 3, 2),
                        "utilization_pct": round(allocated / max(1, total) * 100, 1),
                    }
                )
        except ImportError:
            snapshot["available"] = False
            snapshot["reason"] = "PyTorch not installed"
        return snapshot

    def current_utilization(self) -> Dict:
        return self.sample()

    def summary(self) -> Dict:
        if not self._samples:
            return {"samples": 0}
        recent = self._samples[-10:]
        all_utils: List[float] = []
        for s in recent:
            for gpu in s.get("gpus", []):
                all_utils.append(gpu.get("utilization_pct", 0))
        return {
            "samples": len(self._samples),
            "avg_utilization_pct": round(sum(all_utils) / max(1, len(all_utils)), 1),
            "latest": self._samples[-1] if self._samples else {},
        }
