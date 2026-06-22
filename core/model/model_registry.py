from __future__ import annotations

import logging
from threading import Lock
from typing import Dict, List, Optional

from .model_config import ModelConfig

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Thread-safe in-process registry for ModelConfig objects."""

    _instance: Optional["ModelRegistry"] = None
    _lock: Lock = Lock()

    def __new__(cls) -> "ModelRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._configs: Dict[str, ModelConfig] = {}
        self._initialized = True
        self._seed_defaults()
        logger.info("ModelRegistry initialized with %d defaults", len(self._configs))

    def _seed_defaults(self) -> None:
        defaults = [
            ModelConfig(
                model_id="llama3-8b",
                display_name="LLaMA 3 8B",
                tokenizer_type="llama",
                context_length=8192,
            ),
            ModelConfig(
                model_id="mistral-7b",
                display_name="Mistral 7B",
                tokenizer_type="mistral",
                context_length=8192,
            ),
            ModelConfig(
                model_id="ollama:llama3",
                display_name="Ollama LLaMA 3",
                backend="ollama",
                tokenizer_type="generic",
            ),
        ]
        for cfg in defaults:
            self._configs[cfg.model_id] = cfg

    def register(self, config: ModelConfig) -> None:
        self._configs[config.model_id] = config
        logger.info("Model registered: %s", config.model_id)

    def get(self, model_id: str) -> Optional[ModelConfig]:
        return self._configs.get(model_id)

    def get_or_raise(self, model_id: str) -> ModelConfig:
        cfg = self.get(model_id)
        if cfg is None:
            raise KeyError(f"Model '{model_id}' not found in registry")
        return cfg

    def list_models(self) -> List[Dict]:
        return [
            {
                "model_id": c.model_id,
                "display_name": c.display_name or c.model_id,
                "backend": c.backend,
                "context_length": c.context_length,
            }
            for c in self._configs.values()
        ]

    def unregister(self, model_id: str) -> bool:
        if model_id in self._configs:
            del self._configs[model_id]
            logger.info("Model unregistered: %s", model_id)
            return True
        return False

    def __len__(self) -> int:
        return len(self._configs)
