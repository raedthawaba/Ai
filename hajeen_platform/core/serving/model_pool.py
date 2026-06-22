"""
Model Pool — manages loaded model instances with LRU eviction,
hot swapping, and concurrent access control.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    name: str
    model: Any
    device: str
    loaded_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    request_count: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_used = time.time()
        self.request_count += 1


class ModelPool:
    """Manages a pool of loaded models with LRU eviction."""

    def __init__(self, max_models: int, model_dir: str) -> None:
        self.max_models = max_models
        self.model_dir = model_dir
        self._pool: OrderedDict[str, LoadedModel] = OrderedDict()
        self._loading: Dict[str, asyncio.Event] = {}
        self._pool_lock = asyncio.Lock()

    async def initialize(self) -> None:
        preload = os.environ.get("PRELOAD_MODELS", "").split(",")
        for model_name in preload:
            if model_name.strip():
                await self.load(model_name.strip())
        logger.info("Model pool initialized with %d models", len(self._pool))

    async def get(self, model_name: str) -> Any:
        if model_name in self._pool:
            entry = self._pool[model_name]
            self._pool.move_to_end(model_name)
            entry.touch()
            return entry.model

        if model_name in self._loading:
            await self._loading[model_name].wait()
            if model_name in self._pool:
                return self._pool[model_name].model
            raise RuntimeError(f"Model {model_name} failed to load")

        await self.load(model_name)
        return self._pool[model_name].model

    async def load(self, model_name: str) -> None:
        async with self._pool_lock:
            if model_name in self._pool:
                return

            if len(self._pool) >= self.max_models:
                await self._evict_lru()

            event = asyncio.Event()
            self._loading[model_name] = event

            try:
                logger.info("Loading model: %s", model_name)
                model = await asyncio.to_thread(self._load_model_sync, model_name)
                device = self._assign_device()

                self._pool[model_name] = LoadedModel(
                    name=model_name,
                    model=model,
                    device=device,
                )
                logger.info("Model loaded: %s on %s", model_name, device)
            finally:
                self._loading.pop(model_name, None)
                event.set()

    def _load_model_sync(self, model_name: str) -> Any:
        from core.model.loader import ModelLoader
        loader = ModelLoader(model_dir=self.model_dir)
        return loader.load(model_name)

    def _assign_device(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                device_id = len(self._pool) % torch.cuda.device_count()
                return f"cuda:{device_id}"
        except ImportError:
            pass
        return "cpu"

    async def unload(self, model_name: str) -> None:
        async with self._pool_lock:
            if model_name in self._pool:
                entry = self._pool.pop(model_name)
                await asyncio.to_thread(self._cleanup_model, entry.model)
                logger.info("Unloaded model: %s", model_name)

    async def _evict_lru(self) -> None:
        if not self._pool:
            return
        oldest_name, oldest_entry = next(iter(self._pool.items()))
        self._pool.pop(oldest_name)
        await asyncio.to_thread(self._cleanup_model, oldest_entry.model)
        logger.info("Evicted LRU model: %s", oldest_name)

    def _cleanup_model(self, model: Any) -> None:
        try:
            import torch, gc
            del model
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def list_loaded(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": e.name,
                "device": e.device,
                "loaded_at": e.loaded_at,
                "last_used": e.last_used,
                "request_count": e.request_count,
            }
            for e in self._pool.values()
        ]

    def status(self) -> Dict[str, Any]:
        return {
            "loaded_models": len(self._pool),
            "max_models": self.max_models,
            "models": [e.name for e in self._pool.values()],
        }

    async def cleanup(self) -> None:
        for name in list(self._pool.keys()):
            await self.unload(name)
