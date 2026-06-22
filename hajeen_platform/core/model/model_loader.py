from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from .model_config import ModelBackend, ModelConfig
from .quantization import QuantizationConfig, build_quantization_kwargs

logger = logging.getLogger(__name__)


class ModelLoader:
    """Load model + tokenizer pairs from various backends."""

    def __init__(self) -> None:
        self._loaded: Dict[str, Tuple[Any, Any]] = {}

    def load(self, config: ModelConfig) -> Tuple[Any, Any]:
        """Return (model, tokenizer). Cached after first load."""
        if config.model_id in self._loaded:
            return self._loaded[config.model_id]

        logger.info("Loading model '%s' via backend '%s'", config.model_id, config.backend)

        if config.backend == ModelBackend.HUGGINGFACE:
            pair = self._load_hf(config)
        elif config.backend == ModelBackend.OLLAMA:
            pair = self._load_ollama(config)
        elif config.backend == ModelBackend.LLAMA_CPP:
            pair = self._load_llama_cpp(config)
        else:
            raise ValueError(f"Unsupported backend: {config.backend}")

        self._loaded[config.model_id] = pair
        logger.info("Model loaded: %s", config.model_id)
        return pair

    def _load_hf(self, config: ModelConfig) -> Tuple[Any, Any]:
        try:
            import torch  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            quant_kwargs = build_quantization_kwargs(config)
            device_map = config.device if config.device != "auto" else "auto"

            tokenizer = AutoTokenizer.from_pretrained(
                config.model_id,
                trust_remote_code=config.trust_remote_code,
                use_fast=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                config.model_id,
                device_map=device_map,
                trust_remote_code=config.trust_remote_code,
                torch_dtype=getattr(torch, config.dtype, torch.float16),
                **quant_kwargs,
            )
            model.eval()
            return model, tokenizer
        except ImportError as exc:
            raise RuntimeError(
                "HuggingFace transformers / torch not installed"
            ) from exc

    def _load_ollama(self, config: ModelConfig) -> Tuple[Any, None]:
        try:
            import ollama  # type: ignore

            client = ollama.Client()
            model_name = config.model_id.replace("ollama:", "")
            return client, None
        except ImportError as exc:
            raise RuntimeError("ollama-python not installed") from exc

    def _load_llama_cpp(self, config: ModelConfig) -> Tuple[Any, None]:
        try:
            from llama_cpp import Llama  # type: ignore

            model = Llama(
                model_path=config.model_id,
                n_ctx=config.context_length,
                n_gpu_layers=-1 if "cuda" in config.device else 0,
                verbose=False,
            )
            return model, None
        except ImportError as exc:
            raise RuntimeError("llama-cpp-python not installed") from exc

    def unload(self, model_id: str) -> bool:
        if model_id in self._loaded:
            model, _ = self._loaded.pop(model_id)
            try:
                import torch  # type: ignore
                del model
                torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("Model unloaded: %s", model_id)
            return True
        return False

    def list_loaded(self) -> list[str]:
        return list(self._loaded.keys())
