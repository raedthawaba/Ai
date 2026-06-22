from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelBackend(str, Enum):
    HUGGINGFACE = "huggingface"
    LLAMA_CPP = "llama_cpp"
    OLLAMA = "ollama"
    OPENAI = "openai"
    VLLM = "vllm"
    LOCAL = "local"


class ModelConfig(BaseModel):
    """Full configuration for an AI model."""

    model_id: str = Field(..., description="HuggingFace repo or local path")
    display_name: str = Field(default="", description="Human-readable name")
    backend: ModelBackend = Field(default=ModelBackend.HUGGINGFACE)

    context_length: int = Field(default=4096, ge=512)
    max_new_tokens: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=50, ge=0)
    repetition_penalty: float = Field(default=1.1, ge=1.0)
    stop_sequences: List[str] = Field(default_factory=list)

    quantization: Optional[str] = Field(default=None)
    device: str = Field(default="auto")
    dtype: str = Field(default="float16")
    trust_remote_code: bool = Field(default=False)
    load_in_8bit: bool = Field(default=False)
    load_in_4bit: bool = Field(default=False)

    tokenizer_type: str = Field(default="generic")
    system_prompt: str = Field(default="")
    chat_template: Optional[str] = Field(default=None)

    extra: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @classmethod
    def for_llama(cls, model_id: str, **kwargs: Any) -> "ModelConfig":
        return cls(
            model_id=model_id,
            backend=ModelBackend.HUGGINGFACE,
            tokenizer_type="llama",
            context_length=4096,
            **kwargs,
        )

    @classmethod
    def for_mistral(cls, model_id: str, **kwargs: Any) -> "ModelConfig":
        return cls(
            model_id=model_id,
            backend=ModelBackend.HUGGINGFACE,
            tokenizer_type="mistral",
            context_length=8192,
            **kwargs,
        )

    @classmethod
    def for_ollama(cls, model_id: str, **kwargs: Any) -> "ModelConfig":
        return cls(
            model_id=model_id,
            backend=ModelBackend.OLLAMA,
            tokenizer_type="generic",
            **kwargs,
        )
