"""Phase 8.1 — LLM Settings: إعدادات الـ LLM من environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .base import LLMConfig


@dataclass
class LLMSettings:
    """
    إعدادات LLM الكاملة من env vars أو config dict.

    Variables:
        LLM_PROVIDER        — المزود الافتراضي (default: mock)
        LLM_MODEL           — النموذج الافتراضي
        LLM_API_KEY         — مفتاح API
        LLM_API_BASE        — Base URL مخصص
        LLM_TEMPERATURE     — درجة الإبداع (0-1)
        LLM_MAX_TOKENS      — حد رموز الإخراج
        LLM_TIMEOUT         — مهلة الطلب (ثواني)
        LLM_MAX_RETRIES     — عدد المحاولات
        LLM_STREAM          — تفعيل streaming
        OPENAI_API_KEY      — مفتاح OpenAI (بديل)
        HUGGINGFACE_TOKEN   — رمز HuggingFace
        OLLAMA_BASE_URL     — رابط Ollama المحلي
    """

    provider: str = "hajeen"
    model: str = "hajeen-v1"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.95
    timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0
    stream: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)
    
    # HuggingFace Integration
    hf_dataset_repo: str = os.getenv("HF_DATASET_REPO", "Raedthawaba/hajeen-datasets")
    hf_model_repo: str = os.getenv("HF_MODEL_REPO", "Raedthawaba/hajeen-model")
    hf_token: str = os.getenv("HF_TOKEN", "")

    @classmethod
    def from_env(cls) -> "LLMSettings":
        """تحميل الإعدادات من متغيرات البيئة."""
        # فرض المزود المحلي 'hajeen' بغض النظر عن متغيرات البيئة
        provider = "hajeen"

        # اختيار النموذج الافتراضي بناءً على المزود
        default_models = {
            "openai": "gpt-3.5-turbo",
            "huggingface": "microsoft/DialoGPT-medium",
            "ollama": "llama2",
            "llama_cpp": "llama-2-7b.gguf",
            "mock": "mock-model",
        }

        model = os.getenv("LLM_MODEL", default_models.get(provider, "mock-model"))

        # API key — يدعم متغيرات متعددة
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("HUGGINGFACE_TOKEN")
        )

        api_base = (
            os.getenv("LLM_API_BASE")
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            if provider == "ollama"
            else os.getenv("LLM_API_BASE")
        )

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
            top_p=float(os.getenv("LLM_TOP_P", "0.95")),
            timeout=float(os.getenv("LLM_TIMEOUT", "60.0")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("LLM_RETRY_DELAY", "1.0")),
            stream=os.getenv("LLM_STREAM", "false").lower() == "true",
        )

    def to_llm_config(self) -> LLMConfig:
        """تحويل إلى LLMConfig."""
        return LLMConfig(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key,
            api_base=self.api_base,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            stream=self.stream,
            extra=self.extra,
        )

    def __repr__(self) -> str:
        return (
            f"<LLMSettings provider={self.provider} model={self.model} "
            f"temperature={self.temperature} max_tokens={self.max_tokens}>"
        )
