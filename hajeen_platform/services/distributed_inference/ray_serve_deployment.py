from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Local Model Serving ──────────────────────────────────────────────────────

class LocalModelDeployment:
    """
    Serves a local HuggingFace / GGUF model for inference.
    Priority order: transformers AutoModelForCausalLM → llama-cpp-python → mock.
    Designed for local-only usage (no external APIs).
    """

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        use_4bit: bool = False,
        use_8bit: bool = False,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.use_4bit = use_4bit
        self.use_8bit = use_8bit
        self.model: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self._backend: str = "unloaded"
        logger.info("LocalModelDeployment configured for: %s", model_path)

    def load(self) -> None:
        """Load the model using the best available backend."""
        if not os.path.exists(self.model_path) and not self.model_path.count("/") >= 1:
            raise FileNotFoundError(f"Model not found at: {self.model_path}")

        # Try transformers first
        if self._try_load_transformers():
            return

        # Try llama-cpp for GGUF models
        if self.model_path.endswith(".gguf") and self._try_load_llamacpp():
            return

        logger.warning("Could not load real model — using mock backend.")
        self._backend = "mock"

    def _try_load_transformers(self) -> bool:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            logger.info("Loading model with transformers backend…")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path, trust_remote_code=True
            )

            kwargs: Dict[str, Any] = {"trust_remote_code": True}
            if self.use_4bit:
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
                kwargs["device_map"] = "auto"
            elif self.use_8bit:
                kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
                kwargs["device_map"] = "auto"
            elif self.device == "auto":
                kwargs["device_map"] = "auto"
            else:
                kwargs["device_map"] = self.device

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path, **kwargs
            )
            self._backend = "transformers"
            logger.info("Model loaded via transformers on device=%s", self.device)
            return True
        except Exception as exc:
            logger.warning("Transformers load failed: %s", exc)
            return False

    def _try_load_llamacpp(self) -> bool:
        try:
            from llama_cpp import Llama

            logger.info("Loading GGUF model with llama-cpp-python…")
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=4096,
                n_gpu_layers=-1,
                verbose=False,
            )
            self._backend = "llamacpp"
            logger.info("GGUF model loaded via llama-cpp-python.")
            return True
        except Exception as exc:
            logger.warning("llama-cpp load failed: %s", exc)
            return False

    def generate(self, prompt: str, max_new_tokens: Optional[int] = None) -> str:
        """Generate text from a prompt."""
        tokens = max_new_tokens or self.max_new_tokens
        if self._backend == "transformers":
            return self._generate_transformers(prompt, tokens)
        if self._backend == "llamacpp":
            return self._generate_llamacpp(prompt, tokens)
        return f"[MockModel] Response to: {prompt[:80]}…"

    def _generate_transformers(self, prompt: str, max_new_tokens: int) -> str:
        import torch

        inputs = self.tokenizer(prompt, return_tensors="pt").to(
            next(self.model.parameters()).device
        )
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=self.temperature,
                do_sample=self.temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output_ids[0][inputs["input_ids"].shape[-1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True)

    def _generate_llamacpp(self, prompt: str, max_new_tokens: int) -> str:
        result = self.model(
            prompt,
            max_tokens=max_new_tokens,
            temperature=self.temperature,
            stop=["</s>", "<|endoftext|>"],
        )
        return result["choices"][0]["text"]

    def is_loaded(self) -> bool:
        return self._backend != "unloaded"

    def backend(self) -> str:
        return self._backend


# ── Ray Serve Deployment (optional) ─────────────────────────────────────────

def create_ray_deployment(
    model_path: str,
    num_replicas: int = 1,
    route_prefix: str = "/hajeen-model",
    use_4bit: bool = False,
):
    """
    Creates a Ray Serve deployment class wrapping LocalModelDeployment.
    Only call this when Ray is available and ray.init() has been called.
    """
    try:
        from ray import serve

        @serve.deployment(num_replicas=num_replicas, route_prefix=route_prefix)
        class HajeenModelDeployment:
            def __init__(self):
                self._model = LocalModelDeployment(
                    model_path=model_path, use_4bit=use_4bit
                )
                self._model.load()
                logger.info(
                    "HajeenModelDeployment ready — backend=%s", self._model.backend()
                )

            async def __call__(self, request) -> Dict[str, Any]:
                body = await request.json()
                prompt = body.get("prompt", body.get("text", ""))
                max_tokens = body.get("max_new_tokens", 512)
                if not prompt:
                    return {"error": "prompt is required", "status": 400}
                output = self._model.generate(prompt, max_tokens)
                return {
                    "output": output,
                    "model": model_path,
                    "backend": self._model.backend(),
                }

        return HajeenModelDeployment

    except ImportError:
        logger.warning("Ray not installed — Ray Serve deployment unavailable.")
        return None


# ── Batch Inference Engine ───────────────────────────────────────────────────

class BatchInferenceEngine:
    """Wraps LocalModelDeployment with batching for higher throughput."""

    def __init__(self, deployment: LocalModelDeployment, max_batch: int = 8) -> None:
        self.deployment = deployment
        self.max_batch = max_batch

    def batch_generate(
        self, prompts: List[str], max_new_tokens: int = 256
    ) -> List[str]:
        """Generate responses for a batch of prompts."""
        results: List[str] = []
        for i in range(0, len(prompts), self.max_batch):
            batch = prompts[i: i + self.max_batch]
            for prompt in batch:
                results.append(self.deployment.generate(prompt, max_new_tokens))
        return results
