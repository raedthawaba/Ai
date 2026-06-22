"""
Hajeen Foundation Model
=======================
A fully independent Large Language Model framework built from scratch.
Supports Arabic, English, code, and mixed-language inputs.

Components:
    - Tokenizer (BPE / SentencePiece)
    - Transformer Architecture (RoPE, RMSNorm, Multi-Head Attention)
    - Training Pipeline (mixed precision, distributed ready)
    - Inference Engine (greedy, top-k, top-p, temperature, streaming)
    - Evaluation Framework (perplexity, benchmarks)
    - Checkpoint System (save / load / resume)
    - Quantization (FP32, FP16, INT8, INT4)
    - Export (PyTorch, ONNX)
    - Serving Layer (REST API, batch inference, streaming)
"""

__version__ = "1.0.0"
__author__ = "Hajeen Team"
__license__ = "MIT"

from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenModel, HajeenForCausalLM

__all__ = [
    "HajeenConfig",
    "HajeenModel",
    "HajeenForCausalLM",
    "__version__",
]
