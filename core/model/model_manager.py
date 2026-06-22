"""Model Manager — إدارة مركزية للنماذج مع lazy loading وGPU/CPU fallback."""
from __future__ import annotations

import asyncio
import gc
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class ModelEntry:
    model_id: str
    backend: str
    device: str
    status: ModelStatus = ModelStatus.UNLOADED
    model: Optional[Any] = None
    tokenizer: Optional[Any] = None
    loaded_at: Optional[float] = None
    last_used: Optional[float] = None
    load_time_s: float = 0.0
    error: Optional[str] = None
    memory_mb: float = 0.0
    config: Dict = field(default_factory=dict)

    def touch(self) -> None:
        self.last_used = time.time()

    def is_ready(self) -> bool:
        return self.status == ModelStatus.READY


class ModelManager:
    """
    Singleton لإدارة نماذج الـ LLM مع:
    - lazy loading
    - model registry
    - dynamic switching
    - GPU/CPU fallback
    - quantized model support
    - memory-aware loading
    - model unloading عند الحاجة
    - tokenizer synchronization
    """

    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        max_loaded_models: int = 2,
        memory_limit_mb: float = 8192.0,
        default_device: str = "auto",
    ) -> None:
        self._models: Dict[str, ModelEntry] = {}
        self._max_loaded = max_loaded_models
        self._memory_limit_mb = memory_limit_mb
        self._default_device = self._resolve_device(default_device)
        self._load_lock = asyncio.Lock()
        logger.info(
            "ModelManager initialized: device=%s max_loaded=%d memory_limit=%.0fMB",
            self._default_device, max_loaded_models, memory_limit_mb,
        )

    @classmethod
    def get_instance(cls) -> "ModelManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ─── Device ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    # ─── Registry ─────────────────────────────────────────────────────────────

    def register(
        self,
        model_id: str,
        backend: str = "huggingface",
        device: Optional[str] = None,
        **config: Any,
    ) -> None:
        if model_id in self._models:
            logger.debug("ModelManager: model '%s' already registered", model_id)
            return
        entry = ModelEntry(
            model_id=model_id,
            backend=backend,
            device=device or self._default_device,
            config=config,
        )
        self._models[model_id] = entry
        logger.info("ModelManager: registered '%s' backend=%s", model_id, backend)

    def list_registered(self) -> List[Dict]:
        return [
            {
                "model_id": e.model_id,
                "backend": e.backend,
                "device": e.device,
                "status": e.status.value,
                "loaded_at": e.loaded_at,
                "memory_mb": e.memory_mb,
            }
            for e in self._models.values()
        ]

    # ─── Load / Unload ────────────────────────────────────────────────────────

    async def load(self, model_id: str) -> ModelEntry:
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' غير مسجّل — استخدم register() أولاً")

        entry = self._models[model_id]
        if entry.is_ready():
            entry.touch()
            return entry

        async with self._load_lock:
            # Re-check after acquiring lock
            if entry.is_ready():
                return entry

            # Evict if needed
            self._evict_if_needed()

            entry.status = ModelStatus.LOADING
            t0 = time.perf_counter()
            try:
                model, tokenizer = await asyncio.get_event_loop().run_in_executor(
                    None, self._load_sync, entry
                )
                entry.model = model
                entry.tokenizer = tokenizer
                entry.status = ModelStatus.READY
                entry.loaded_at = time.time()
                entry.last_used = time.time()
                entry.load_time_s = round(time.perf_counter() - t0, 2)
                entry.memory_mb = self._estimate_memory(entry)
                logger.info(
                    "ModelManager: '%s' loaded in %.2fs on %s",
                    model_id, entry.load_time_s, entry.device,
                )
            except Exception as exc:
                entry.status = ModelStatus.ERROR
                entry.error = str(exc)
                logger.error("ModelManager: load failed '%s': %s", model_id, exc)
                raise

        return entry

    def _load_sync(self, entry: ModelEntry) -> Tuple[Any, Any]:
        from core.model.model_loader import ModelLoader
        from core.model.model_config import ModelConfig, ModelBackend

        backend_map = {
            "huggingface": ModelBackend.HUGGINGFACE,
            "ollama": ModelBackend.OLLAMA,
            "llama_cpp": ModelBackend.LLAMA_CPP,
        }
        cfg = ModelConfig(
            model_id=entry.model_id,
            backend=backend_map.get(entry.backend, ModelBackend.HUGGINGFACE),
            device=entry.device,
            **{k: v for k, v in entry.config.items() if k in (
                "dtype", "quantization", "trust_remote_code", "max_length"
            )},
        )
        loader = ModelLoader()
        return loader.load(cfg)

    def unload(self, model_id: str) -> bool:
        entry = self._models.get(model_id)
        if entry is None or not entry.is_ready():
            return False
        entry.status = ModelStatus.UNLOADING
        entry.model = None
        entry.tokenizer = None
        entry.status = ModelStatus.UNLOADED
        entry.memory_mb = 0.0
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        logger.info("ModelManager: '%s' unloaded", model_id)
        return True

    def _evict_if_needed(self) -> None:
        loaded = [e for e in self._models.values() if e.is_ready()]
        total_mem = sum(e.memory_mb for e in loaded)

        if len(loaded) >= self._max_loaded or total_mem >= self._memory_limit_mb:
            # Evict LRU
            lru = min(loaded, key=lambda e: e.last_used or 0)
            logger.info("ModelManager: evicting LRU model '%s'", lru.model_id)
            self.unload(lru.model_id)

    @staticmethod
    def _estimate_memory(entry: ModelEntry) -> float:
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.memory_allocated() / 1024 / 1024
        except Exception:
            pass
        return 0.0

    # ─── Switch & Get ─────────────────────────────────────────────────────────

    async def get_model(self, model_id: str) -> Optional[Any]:
        entry = await self.load(model_id)
        entry.touch()
        return entry.model

    async def get_tokenizer(self, model_id: str) -> Optional[Any]:
        entry = await self.load(model_id)
        return entry.tokenizer

    async def switch(self, model_id: str, new_model_id: str) -> None:
        """يُبدّل نموذجاً بآخر — يُفرّغ القديم أولاً."""
        if model_id in self._models:
            self.unload(model_id)
        await self.load(new_model_id)
        logger.info("ModelManager: switched '%s' → '%s'", model_id, new_model_id)

    # ─── Health ───────────────────────────────────────────────────────────────

    def health(self) -> Dict:
        loaded = [e for e in self._models.values() if e.is_ready()]
        return {
            "registered": len(self._models),
            "loaded": len(loaded),
            "device": self._default_device,
            "total_memory_mb": round(sum(e.memory_mb for e in loaded), 1),
            "models": {e.model_id: e.status.value for e in self._models.values()},
        }
