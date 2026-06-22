"""
local_inference_engine.py — محرك الاستدلال المحلي لـ Hajeen Foundation Model
يعمل بشكل مستقل بدون Ollama أو Qwen أو أي مزود خارجي
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

LOCAL_ONLY_MODE = os.getenv("HAJEEN_LOCAL_ONLY", "true").lower() == "true"


@dataclass
class LocalInferenceConfig:
    """إعدادات محرك الاستدلال المحلي."""
    model_path: Optional[str] = None
    tokenizer_path: Optional[str] = None
    device: str = "auto"
    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.1
    do_sample: bool = True
    use_cache: bool = True
    batch_size: int = 1
    dtype: str = "float32"


@dataclass
class LocalResponse:
    """استجابة النموذج المحلي."""
    content: str
    model: str = "HajeenFoundationModel"
    provider: str = "local"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    device: str = "cpu"


class GreedySampler:
    """Greedy decoding لإنتاج النص."""

    def __init__(self, temperature: float = 1.0, top_p: float = 1.0, top_k: int = 0):
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k

    def sample(self, logits: torch.Tensor) -> int:
        """اختيار التوكن التالي من logits."""
        logits = logits.float()

        if self.temperature != 1.0:
            logits = logits / self.temperature

        if self.top_k > 0:
            top_k = min(self.top_k, logits.size(-1))
            indices_to_remove = logits < torch.topk(logits, top_k)[0][..., -1, None]
            logits = logits.masked_fill(indices_to_remove, float("-inf"))

        if self.top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
            sorted_indices_to_remove = cumulative_probs > self.top_p
            sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
            sorted_indices_to_remove[..., 0] = 0
            indices_to_remove = sorted_indices_to_remove.scatter(
                0, sorted_indices, sorted_indices_to_remove
            )
            logits = logits.masked_fill(indices_to_remove, float("-inf"))

        probs = F.softmax(logits, dim=-1)
        token_id = torch.multinomial(probs, num_samples=1).item()
        return int(token_id)


class LocalInferenceEngine:
    """
    محرك الاستدلال المحلي المستقل لـ Hajeen Foundation Model.

    يعمل فقط بالأوزان المحلية بدون:
    - Ollama
    - Qwen
    - OpenAI
    - Cohere
    - أي مزود خارجي آخر
    """

    DISABLED_PROVIDERS = ["ollama", "qwen", "openai", "cohere", "anthropic", "gemini"]

    def __init__(
        self,
        model: Optional[nn.Module] = None,
        tokenizer=None,
        config: Optional[LocalInferenceConfig] = None,
    ):
        self.config = config or LocalInferenceConfig()
        self.model = model
        self.tokenizer = tokenizer
        self._is_loaded = model is not None and tokenizer is not None

        self.device = self._resolve_device()
        self.sampler = GreedySampler(
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            top_k=self.config.top_k,
        )

        if LOCAL_ONLY_MODE:
            self._disable_external_providers()

        if self.model is not None:
            self.model.to(self.device)
            self.model.eval()

        logger.info(f"🤖 LocalInferenceEngine جاهز — Device: {self.device}")
        if LOCAL_ONLY_MODE:
            logger.info("🔒 وضع LOCAL ONLY مُفعَّل — جميع المزودين الخارجيين معطَّلون")

    def _resolve_device(self) -> torch.device:
        """تحديد الجهاز المناسب للاستدلال."""
        device_str = self.config.device
        if device_str == "auto":
            if torch.cuda.is_available():
                device_str = "cuda"
                logger.info(f"🚀 GPU متاح: {torch.cuda.get_device_name(0)}")
            else:
                device_str = "cpu"
                logger.info("💻 استخدام CPU")
        return torch.device(device_str)

    def _disable_external_providers(self) -> None:
        """تعطيل جميع المزودين الخارجيين."""
        for provider in self.DISABLED_PROVIDERS:
            env_key = f"HAJEEN_DISABLE_{provider.upper()}"
            os.environ[env_key] = "true"
        logger.info(f"🚫 مزودون معطَّلون: {', '.join(self.DISABLED_PROVIDERS)}")

    def load_model(
        self,
        model_path: Optional[str] = None,
        tokenizer_path: Optional[str] = None,
    ) -> None:
        """
        تحميل النموذج والـ Tokenizer من الأوزان المحلية.
        """
        model_path = model_path or self.config.model_path
        tokenizer_path = tokenizer_path or self.config.tokenizer_path

        if model_path and Path(model_path).exists():
            logger.info(f"⬇️  تحميل أوزان النموذج من: {model_path}")
            try:
                state_dict = torch.load(model_path, map_location=self.device)
                if isinstance(state_dict, dict) and "model_state_dict" in state_dict:
                    state_dict = state_dict["model_state_dict"]
                if self.model is not None:
                    self.model.load_state_dict(state_dict)
                    self.model.to(self.device)
                    self.model.eval()
                    self._is_loaded = True
                    logger.info("✅ تم تحميل أوزان النموذج")
            except Exception as e:
                logger.error(f"❌ فشل تحميل الأوزان: {e}")
        else:
            logger.warning(f"⚠️  مسار الأوزان غير موجود: {model_path} — سيتم استخدام الأوزان الافتراضية")

        if tokenizer_path and Path(tokenizer_path).exists():
            logger.info(f"⬇️  تحميل Tokenizer من: {tokenizer_path}")
            try:
                from tokenizers import Tokenizer
                self.tokenizer = Tokenizer.from_file(
                    str(Path(tokenizer_path) / "tokenizer.json")
                    if Path(tokenizer_path).is_dir()
                    else tokenizer_path
                )
                logger.info("✅ تم تحميل الـ Tokenizer")
            except Exception as e:
                logger.error(f"❌ فشل تحميل الـ Tokenizer: {e}")

    def load_from_huggingface(self, model_version: str = "v1.0") -> None:
        """تحميل النموذج والـ Tokenizer من HuggingFace (أوزان محلية بعد التحميل)."""
        try:
            from cloud.model_manager import ModelManager
            mm = ModelManager()
            local_dir = mm.download_checkpoint(local_dir=f"./model_weights/{model_version}")
            self.load_model(
                model_path=f"{local_dir}/model/model.pt",
                tokenizer_path=f"{local_dir}/tokenizer",
            )
            logger.info(f"✅ تم تحميل النموذج من HuggingFace: {model_version}")
        except Exception as e:
            logger.error(f"❌ فشل تحميل من HuggingFace: {e}")

    @torch.no_grad()
    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> LocalResponse:
        """
        توليد نص من النموذج المحلي.
        يعمل فقط بالأوزان المحلية — لا يتصل بأي خدمة خارجية.
        """
        if not self._is_loaded or self.model is None:
            return self._fallback_response(prompt)

        start_time = time.time()
        max_new = max_new_tokens or self.config.max_new_tokens
        temp = temperature or self.config.temperature
        self.sampler.temperature = temp

        if self.tokenizer is None:
            input_ids = [ord(c) % 1000 for c in prompt[:100]]
        else:
            encoded = self.tokenizer.encode(prompt)
            input_ids = encoded.ids if hasattr(encoded, "ids") else encoded

        input_tensor = torch.tensor([input_ids], dtype=torch.long).to(self.device)
        prompt_token_count = len(input_ids)

        generated_ids = []
        eos_token_id = 3

        for _ in range(max_new):
            current_input = torch.cat([
                input_tensor,
                torch.tensor([generated_ids], dtype=torch.long).to(self.device)
            ], dim=1) if generated_ids else input_tensor

            try:
                outputs = self.model(input_ids=current_input)
                logits = outputs["logits"] if isinstance(outputs, dict) else outputs
                next_token_logits = logits[0, -1, :]
            except Exception as e:
                logger.error(f"❌ خطأ في الاستدلال: {e}")
                break

            next_token_id = self.sampler.sample(next_token_logits)
            generated_ids.append(next_token_id)

            if next_token_id == eos_token_id:
                break

        if self.tokenizer and generated_ids:
            generated_text = self.tokenizer.decode(generated_ids)
        else:
            generated_text = " ".join(str(i) for i in generated_ids[:50])

        latency_ms = (time.time() - start_time) * 1000

        return LocalResponse(
            content=generated_text,
            model="HajeenFoundationModel",
            provider="local",
            prompt_tokens=prompt_token_count,
            completion_tokens=len(generated_ids),
            total_tokens=prompt_token_count + len(generated_ids),
            latency_ms=round(latency_ms, 2),
            finish_reason="eos" if generated_ids and generated_ids[-1] == eos_token_id else "length",
            device=str(self.device),
        )

    def _fallback_response(self, prompt: str) -> LocalResponse:
        """استجابة احتياطية عندما لا يكون النموذج محملاً."""
        logger.warning("⚠️  النموذج غير محمل — استجابة احتياطية")
        return LocalResponse(
            content=(
                "[Hajeen Foundation Model — Local Mode]\n"
                "النموذج غير محمل بعد. يرجى:\n"
                "1. تدريب النموذج باستخدام train_hajeen_cloud.py\n"
                "2. تحميل الأوزان من HuggingFace\n"
                "3. أو وضع الأوزان في ./model_weights/"
            ),
            provider="local_fallback",
            finish_reason="no_model",
        )

    async def generate_async(self, prompt: str, **kwargs) -> LocalResponse:
        """نسخة async من generate."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.generate(prompt, **kwargs))

    async def stream_generate(
        self, prompt: str, **kwargs
    ) -> AsyncGenerator[str, None]:
        """Streaming بسيط — يولد token بـ token."""
        response = self.generate(prompt, **kwargs)
        words = response.content.split()
        for word in words:
            yield word + " "
            import asyncio
            await asyncio.sleep(0.01)

    def get_model_info(self) -> Dict:
        """معلومات النموذج الحالي."""
        param_count = sum(p.numel() for p in self.model.parameters()) if self.model else 0
        return {
            "model_name": "HajeenFoundationModel",
            "provider": "local",
            "device": str(self.device),
            "is_loaded": self._is_loaded,
            "parameter_count": param_count,
            "parameter_count_human": f"{param_count / 1e6:.1f}M" if param_count > 0 else "N/A",
            "local_only_mode": LOCAL_ONLY_MODE,
            "disabled_providers": self.DISABLED_PROVIDERS if LOCAL_ONLY_MODE else [],
            "dtype": self.config.dtype,
        }
