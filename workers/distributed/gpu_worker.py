"""
GPU Worker — handles GPU-intensive tasks: inference, embedding generation,
model training, and quantization.
"""
from __future__ import annotations

import gc
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
    GPU_COUNT = torch.cuda.device_count()
except ImportError:
    TORCH_AVAILABLE = False
    GPU_COUNT = 0


class GPUMemoryManager:
    """Manages GPU memory allocation across tasks."""

    def __init__(self) -> None:
        self.allocated: Dict[str, Dict[str, Any]] = {}
        self.device_utilization: Dict[int, float] = {}

    def get_best_device(self, required_memory_gb: float = 4.0) -> int:
        if not TORCH_AVAILABLE or GPU_COUNT == 0:
            raise RuntimeError("No GPU available")

        best_device = 0
        best_free = 0.0

        for device_id in range(GPU_COUNT):
            props = torch.cuda.get_device_properties(device_id)
            total = props.total_memory / (1024 ** 3)
            allocated = torch.cuda.memory_allocated(device_id) / (1024 ** 3)
            free = total - allocated

            if free >= required_memory_gb and free > best_free:
                best_free = free
                best_device = device_id

        if best_free < required_memory_gb:
            raise RuntimeError(
                f"Insufficient GPU memory: need {required_memory_gb}GB, "
                f"best available {best_free:.1f}GB"
            )

        return best_device

    @contextmanager
    def reserve_device(
        self, device_id: int, task_id: str
    ) -> Generator[int, None, None]:
        self.allocated[task_id] = {
            "device_id": device_id,
            "start_time": time.time(),
        }
        try:
            yield device_id
        finally:
            self.allocated.pop(task_id, None)
            if TORCH_AVAILABLE:
                with torch.cuda.device(device_id):
                    torch.cuda.empty_cache()
            gc.collect()

    def get_memory_stats(self) -> Dict[str, Any]:
        if not TORCH_AVAILABLE:
            return {"gpu_available": False}

        stats: Dict[str, Any] = {"gpu_available": True, "devices": []}
        for device_id in range(GPU_COUNT):
            props = torch.cuda.get_device_properties(device_id)
            total = props.total_memory / (1024 ** 3)
            allocated = torch.cuda.memory_allocated(device_id) / (1024 ** 3)
            reserved = torch.cuda.memory_reserved(device_id) / (1024 ** 3)

            stats["devices"].append(
                {
                    "device_id": device_id,
                    "name": props.name,
                    "total_gb": round(total, 2),
                    "allocated_gb": round(allocated, 2),
                    "reserved_gb": round(reserved, 2),
                    "free_gb": round(total - allocated, 2),
                    "utilization_pct": round((allocated / total) * 100, 1),
                }
            )
        return stats


_memory_manager = GPUMemoryManager()


class GPUWorker:
    """Worker that processes GPU-intensive tasks."""

    def __init__(
        self,
        worker_id: str,
        model_cache: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.worker_id = worker_id
        self.model_cache = model_cache or {}
        self.memory_manager = _memory_manager
        self.task_count = 0
        self.error_count = 0

    def run_inference(
        self,
        model_name: str,
        inputs: List[str],
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        config = generation_config or {}

        try:
            required_gb = config.get("required_memory_gb", 8.0)
            device_id = self.memory_manager.get_best_device(required_gb)

            with self.memory_manager.reserve_device(
                device_id, f"{self.worker_id}_{self.task_count}"
            ):
                model = self._load_model(model_name, device_id)
                outputs = self._generate(model, inputs, config, device_id)
                self.task_count += 1

                return {
                    "status": "success",
                    "outputs": outputs,
                    "model": model_name,
                    "device": device_id,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    "batch_size": len(inputs),
                }

        except Exception as exc:
            self.error_count += 1
            logger.exception("GPU inference failed: %s", exc)
            raise

    def _load_model(self, model_name: str, device_id: int) -> Any:
        cache_key = f"{model_name}:{device_id}"
        if cache_key in self.model_cache:
            return self.model_cache[cache_key]

        logger.info("Loading model %s on device %d", model_name, device_id)
        # Model loading logic — integrated with core/model/ layer
        from core.model.loader import ModelLoader
        loader = ModelLoader()
        model = loader.load(model_name, device=f"cuda:{device_id}")
        self.model_cache[cache_key] = model
        return model

    def _generate(
        self,
        model: Any,
        inputs: List[str],
        config: Dict[str, Any],
        device_id: int,
    ) -> List[str]:
        max_tokens = config.get("max_tokens", 512)
        temperature = config.get("temperature", 0.7)
        top_p = config.get("top_p", 0.9)

        outputs = model.generate(
            inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=temperature > 0,
        )
        return outputs

    def run_embedding(
        self,
        texts: List[str],
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            device_id = self.memory_manager.get_best_device(required_memory_gb=2.0)
            with self.memory_manager.reserve_device(
                device_id, f"embed_{self.task_count}"
            ):
                from core.embeddings.generator import EmbeddingGenerator
                gen = EmbeddingGenerator(model_name=model_name, device=f"cuda:{device_id}")
                embeddings = gen.encode(texts)
                self.task_count += 1

                return {
                    "status": "success",
                    "embeddings": embeddings,
                    "model": model_name,
                    "count": len(texts),
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                }
        except Exception as exc:
            self.error_count += 1
            logger.exception("Embedding generation failed: %s", exc)
            raise

    def health_check(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": "healthy",
            "task_count": self.task_count,
            "error_count": self.error_count,
            "gpu_stats": self.memory_manager.get_memory_stats(),
            "cached_models": list(self.model_cache.keys()),
        }
