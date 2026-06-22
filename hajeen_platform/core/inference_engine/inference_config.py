from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class InferenceConfig(BaseModel):
    """All sampling / generation hyper-parameters in one place."""

    max_new_tokens: int = Field(default=512, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=50, ge=0)
    repetition_penalty: float = Field(default=1.1, ge=1.0)
    stop_sequences: List[str] = Field(default_factory=list)
    stream: bool = Field(default=False)
    seed: Optional[int] = Field(default=None)
    timeout_seconds: float = Field(default=120.0, ge=1.0)
    num_beams: int = Field(default=1, ge=1)
    do_sample: bool = Field(default=True)
    length_penalty: float = Field(default=1.0)
    early_stopping: bool = Field(default=False)

    model_config = {"extra": "allow"}

    @classmethod
    def greedy(cls) -> "InferenceConfig":
        return cls(temperature=1.0, top_p=1.0, top_k=0, do_sample=False)

    @classmethod
    def creative(cls) -> "InferenceConfig":
        return cls(temperature=1.2, top_p=0.95, top_k=100, repetition_penalty=1.05)

    @classmethod
    def precise(cls) -> "InferenceConfig":
        return cls(temperature=0.3, top_p=0.85, top_k=20)
