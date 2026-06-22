from __future__ import annotations

from enum import Enum
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .model_config import ModelConfig


class QuantizationType(str, Enum):
    NONE = "none"
    INT8 = "int8"
    INT4 = "int4"
    GPTQ = "gptq"
    AWQ = "awq"
    GGUF = "gguf"


class QuantizationConfig:
    """Carries quantization parameters for a model load."""

    def __init__(
        self,
        quant_type: QuantizationType = QuantizationType.NONE,
        bits: int = 16,
        group_size: int = 128,
        double_quant: bool = True,
        quant_type_bnb: str = "nf4",
    ) -> None:
        self.quant_type = quant_type
        self.bits = bits
        self.group_size = group_size
        self.double_quant = double_quant
        self.quant_type_bnb = quant_type_bnb

    def to_bitsandbytes_config(self) -> Any:
        """Return a BitsAndBytesConfig for 4-bit or 8-bit quantization."""
        try:
            from transformers import BitsAndBytesConfig  # type: ignore
        except ImportError as exc:
            raise RuntimeError("transformers not installed") from exc

        if self.quant_type == QuantizationType.INT8:
            return BitsAndBytesConfig(load_in_8bit=True)
        if self.quant_type == QuantizationType.INT4:
            return BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type=self.quant_type_bnb,
                bnb_4bit_use_double_quant=self.double_quant,
            )
        return None

    def __repr__(self) -> str:
        return f"QuantizationConfig(type={self.quant_type}, bits={self.bits})"


def build_quantization_kwargs(config: "ModelConfig") -> Dict[str, Any]:
    """Convert ModelConfig flags into kwargs for from_pretrained."""
    kwargs: Dict[str, Any] = {}
    if config.load_in_4bit or config.load_in_8bit:
        try:
            from transformers import BitsAndBytesConfig  # type: ignore

            if config.load_in_4bit:
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )
            elif config.load_in_8bit:
                kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        except ImportError:
            pass
    return kwargs
