"""
llama.cpp Server — CPU/GPU inference using llama.cpp for quantized models.
Ideal for running GGUF models with minimal VRAM.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama, LlamaGrammar
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False
    logger.warning("llama-cpp-python not installed")


class LlamaCppServer:
    """Inference server for GGUF quantized models via llama.cpp."""

    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 4096,
        n_threads: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        if not LLAMA_CPP_AVAILABLE:
            raise RuntimeError("llama-cpp-python not installed. Run: pip install llama-cpp-python")

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        self.model_path = model_path
        self._model: Optional[Llama] = None
        self._init_kwargs = {
            "model_path": model_path,
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "n_threads": n_threads or os.cpu_count(),
            "verbose": verbose,
        }

    def load(self) -> None:
        logger.info("Loading llama.cpp model: %s", self.model_path)
        self._model = Llama(**self._init_kwargs)
        logger.info("llama.cpp model loaded successfully")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        echo: bool = False,
    ) -> str:
        if not self._model:
            raise RuntimeError("Model not loaded — call load() first")

        output = self._model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or [],
            echo=echo,
        )
        return output["choices"][0]["text"]

    def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        if not self._model:
            raise RuntimeError("Model not loaded")

        stream = self._model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or [],
            stream=True,
        )
        for chunk in stream:
            token = chunk["choices"][0].get("text", "")
            if token:
                yield token

    def get_embeddings(self, text: str) -> List[float]:
        if not self._model:
            raise RuntimeError("Model not loaded")
        return self._model.create_embedding(text)["data"][0]["embedding"]

    def unload(self) -> None:
        self._model = None
        import gc
        gc.collect()
        logger.info("llama.cpp model unloaded")
