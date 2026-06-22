"""
Quantization Manager — manages model quantization (INT8, INT4, GPTQ, AWQ)
to reduce memory footprint and increase inference throughput.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class QuantizationType(str, Enum):
    FP16 = "fp16"
    BF16 = "bf16"
    INT8 = "int8"
    INT4 = "int4"
    GPTQ_4BIT = "gptq_4bit"
    GPTQ_8BIT = "gptq_8bit"
    AWQ_4BIT = "awq_4bit"
    GGUF_Q4_K_M = "gguf_q4_k_m"
    GGUF_Q5_K_M = "gguf_q5_k_m"
    GGUF_Q8_0 = "gguf_q8_0"


@dataclass
class QuantizationConfig:
    quant_type: QuantizationType
    bits: int
    group_size: int = 128
    desc_act: bool = False
    sym: bool = True
    calibration_samples: int = 128


QUANT_CONFIGS: Dict[QuantizationType, QuantizationConfig] = {
    QuantizationType.INT8: QuantizationConfig(quant_type=QuantizationType.INT8, bits=8),
    QuantizationType.INT4: QuantizationConfig(quant_type=QuantizationType.INT4, bits=4, group_size=128),
    QuantizationType.GPTQ_4BIT: QuantizationConfig(
        quant_type=QuantizationType.GPTQ_4BIT, bits=4, group_size=128, desc_act=True
    ),
    QuantizationType.AWQ_4BIT: QuantizationConfig(
        quant_type=QuantizationType.AWQ_4BIT, bits=4, group_size=128
    ),
}

MEMORY_REDUCTION: Dict[QuantizationType, float] = {
    QuantizationType.FP16: 1.0,
    QuantizationType.BF16: 1.0,
    QuantizationType.INT8: 0.5,
    QuantizationType.INT4: 0.25,
    QuantizationType.GPTQ_4BIT: 0.25,
    QuantizationType.AWQ_4BIT: 0.25,
    QuantizationType.GGUF_Q4_K_M: 0.25,
    QuantizationType.GGUF_Q5_K_M: 0.31,
    QuantizationType.GGUF_Q8_0: 0.5,
}


class QuantizationManager:
    """Manages model quantization workflows."""

    def __init__(self, model_dir: str, output_dir: str) -> None:
        self.model_dir = Path(model_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def quantize(
        self,
        model_name: str,
        quant_type: QuantizationType,
        calibration_data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        start = time.time()
        config = QUANT_CONFIGS.get(quant_type)
        output_path = self.output_dir / f"{model_name.replace('/', '_')}_{quant_type.value}"

        logger.info("Quantizing %s to %s", model_name, quant_type.value)

        if quant_type in (QuantizationType.GPTQ_4BIT, QuantizationType.GPTQ_8BIT):
            result = self._quantize_gptq(model_name, config, output_path, calibration_data)
        elif quant_type == QuantizationType.AWQ_4BIT:
            result = self._quantize_awq(model_name, config, output_path, calibration_data)
        elif quant_type in (QuantizationType.INT8, QuantizationType.INT4):
            result = self._quantize_bitsandbytes(model_name, quant_type, output_path)
        else:
            raise ValueError(f"Unsupported quantization type: {quant_type}")

        duration = time.time() - start
        memory_factor = MEMORY_REDUCTION.get(quant_type, 1.0)

        return {
            "model": model_name,
            "quant_type": quant_type.value,
            "output_path": str(output_path),
            "duration_seconds": round(duration, 1),
            "estimated_memory_reduction": f"{(1 - memory_factor) * 100:.0f}%",
            **result,
        }

    def _quantize_gptq(
        self,
        model_name: str,
        config: QuantizationConfig,
        output_path: Path,
        calibration_data: Optional[Any],
    ) -> Dict[str, Any]:
        try:
            from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_name)
            quant_config = BaseQuantizeConfig(
                bits=config.bits,
                group_size=config.group_size,
                desc_act=config.desc_act,
            )
            model = AutoGPTQForCausalLM.from_pretrained(model_name, quant_config)

            examples = calibration_data or self._default_calibration(tokenizer)
            model.quantize(examples)
            model.save_quantized(str(output_path), use_safetensors=True)
            tokenizer.save_pretrained(str(output_path))

            return {"status": "success", "method": "gptq", "bits": config.bits}
        except ImportError:
            raise RuntimeError("auto-gptq not installed: pip install auto-gptq")

    def _quantize_awq(
        self,
        model_name: str,
        config: QuantizationConfig,
        output_path: Path,
        calibration_data: Optional[Any],
    ) -> Dict[str, Any]:
        try:
            from awq import AutoAWQForCausalLM
            from transformers import AutoTokenizer

            model = AutoAWQForCausalLM.from_pretrained(model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)

            quant_config = {
                "zero_point": True,
                "q_group_size": config.group_size,
                "w_bit": config.bits,
                "version": "GEMM",
            }
            model.quantize(tokenizer, quant_config=quant_config)
            model.save_quantized(str(output_path))
            tokenizer.save_pretrained(str(output_path))

            return {"status": "success", "method": "awq", "bits": config.bits}
        except ImportError:
            raise RuntimeError("autoawq not installed: pip install autoawq")

    def _quantize_bitsandbytes(
        self,
        model_name: str,
        quant_type: QuantizationType,
        output_path: Path,
    ) -> Dict[str, Any]:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            bnb_config = BitsAndBytesConfig(
                load_in_8bit=(quant_type == QuantizationType.INT8),
                load_in_4bit=(quant_type == QuantizationType.INT4),
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map="auto",
            )
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model.save_pretrained(str(output_path))
            tokenizer.save_pretrained(str(output_path))

            return {"status": "success", "method": "bitsandbytes", "bits": 8 if quant_type == QuantizationType.INT8 else 4}
        except ImportError:
            raise RuntimeError("bitsandbytes not installed: pip install bitsandbytes")

    def _default_calibration(self, tokenizer: Any) -> Any:
        texts = [
            "The capital of France is Paris.",
            "Machine learning is a subset of artificial intelligence.",
            "Large language models are trained on vast datasets.",
        ]
        return [tokenizer(t, return_tensors="pt") for t in texts]
