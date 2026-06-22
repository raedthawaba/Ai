"""
exporter.py — Export Hajeen models to PyTorch and ONNX formats.

Supported formats:
    - PyTorch TorchScript (.pt) — for deployment without Python
    - ONNX (.onnx) — for cross-platform serving (TensorRT, ONNX Runtime, etc.)
    - SafeTensors weights — for sharing model weights
    - Hugging-Face compatible format — weights + config JSON

Usage:
    exporter = HajeenExporter(model, tokenizer)
    exporter.export_pytorch("outputs/hajeen.pt")
    exporter.export_onnx("outputs/hajeen.onnx", seq_len=128)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn


@dataclass
class ExportConfig:
    """Configuration for model export."""
    output_dir: str = "exports"
    seq_len: int = 128              # Sequence length for ONNX tracing
    batch_size: int = 1
    opset_version: int = 17         # ONNX opset
    simplify_onnx: bool = False     # Requires onnxsim
    device: str = "cpu"


class HajeenExporter:
    """
    Export HajeenForCausalLM to various deployment formats.

    Args:
        model: HajeenForCausalLM instance.
        tokenizer: HajeenTokenizer instance (optional, used for ONNX input example).
        config: ExportConfig.
    """

    def __init__(
        self,
        model: nn.Module,
        tokenizer=None,
        config: Optional[ExportConfig] = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.config = config or ExportConfig()
        self.device = torch.device(self.config.device)
        self.model.eval().to(self.device)

    def _ensure_dir(self, path: str) -> str:
        """Create directory for output path."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return path

    # ── PyTorch weights ────────────────────────────────────────────────────

    def export_weights(self, output_path: str) -> str:
        """
        Export model weights as a plain PyTorch state dict (.pt file).

        This is the simplest export — reloadable with load_state_dict().
        """
        self._ensure_dir(output_path)
        torch.save(self.model.state_dict(), output_path)
        size_mb = os.path.getsize(output_path) / (1024 ** 2)
        print(f"[HajeenExporter] Weights saved: {output_path} ({size_mb:.1f} MB)")
        return output_path

    # ── TorchScript ────────────────────────────────────────────────────────

    def export_pytorch(self, output_path: str) -> str:
        """
        Export model as a TorchScript module (.pt).

        TorchScript allows running the model without the full Python source.
        Suitable for C++ deployment.

        Args:
            output_path: Path to save the .pt file.

        Returns:
            Absolute path to saved file.
        """
        self._ensure_dir(output_path)

        # Create a traced wrapper (forward with input_ids only)
        class TracingWrapper(nn.Module):
            def __init__(self, m):
                super().__init__()
                self.m = m

            def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
                out = self.m(input_ids=input_ids)
                return out["logits"]

        wrapper = TracingWrapper(self.model).eval().to(self.device)

        dummy = torch.randint(
            0, self.model.config.vocab_size,
            (self.config.batch_size, self.config.seq_len),
            device=self.device,
        )

        try:
            traced = torch.jit.trace(wrapper, dummy, strict=False)
            traced.save(output_path)
            size_mb = os.path.getsize(output_path) / (1024 ** 2)
            print(f"[HajeenExporter] TorchScript saved: {output_path} ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"[HajeenExporter] TorchScript tracing failed: {e}")
            print("  Falling back to weights-only export.")
            return self.export_weights(output_path.replace(".pt", "_weights.pt"))

        return output_path

    # ── ONNX ──────────────────────────────────────────────────────────────

    def export_onnx(self, output_path: str) -> str:
        """
        Export model to ONNX format.

        Compatible with ONNX Runtime, TensorRT, and OpenVINO.

        Args:
            output_path: Path to save the .onnx file.

        Returns:
            Absolute path to saved file.
        """
        try:
            import onnx
        except ImportError:
            raise ImportError(
                "ONNX export requires 'onnx' package. Install with: pip install onnx"
            )

        self._ensure_dir(output_path)

        dummy_input = torch.randint(
            0, self.model.config.vocab_size,
            (self.config.batch_size, self.config.seq_len),
            device=self.device,
        )

        class ONNXWrapper(nn.Module):
            def __init__(self, m):
                super().__init__()
                self.m = m

            def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
                return self.m(input_ids=input_ids)["logits"]

        wrapper = ONNXWrapper(self.model).eval().to(self.device)

        torch.onnx.export(
            wrapper,
            dummy_input,
            output_path,
            input_names=["input_ids"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "logits":    {0: "batch_size", 1: "sequence_length"},
            },
            opset_version=self.config.opset_version,
            do_constant_folding=True,
        )

        # Validate
        model_onnx = onnx.load(output_path)
        onnx.checker.check_model(model_onnx)

        if self.config.simplify_onnx:
            try:
                from onnxsim import simplify
                model_onnx, ok = simplify(model_onnx)
                if ok:
                    onnx.save(model_onnx, output_path)
                    print("  ONNX model simplified successfully.")
            except ImportError:
                print("  onnxsim not installed — skipping simplification.")

        size_mb = os.path.getsize(output_path) / (1024 ** 2)
        print(f"[HajeenExporter] ONNX saved: {output_path} ({size_mb:.1f} MB)")
        return output_path

    # ── Full export (config + weights + tokenizer) ────────────────────────

    def export_full(self, directory: str) -> str:
        """
        Export everything needed to load and run the model:
            - model weights (model.pt)
            - config.json
            - tokenizer vocab + merges (if tokenizer available)

        Args:
            directory: Output directory.

        Returns:
            Absolute path to output directory.
        """
        os.makedirs(directory, exist_ok=True)

        # Weights
        self.export_weights(os.path.join(directory, "model.pt"))

        # Config
        if hasattr(self.model, "config"):
            self.model.config.to_json(os.path.join(directory, "config.json"))
            print(f"[HajeenExporter] Config saved: {directory}/config.json")

        # Tokenizer
        if self.tokenizer is not None and hasattr(self.tokenizer, "_backend"):
            tok_dir = os.path.join(directory, "tokenizer")
            self.tokenizer._backend.save(tok_dir)

        # Export manifest
        manifest = {
            "format": "hajeen_full",
            "version": "1.0.0",
            "files": {
                "weights": "model.pt",
                "config": "config.json",
                "tokenizer": "tokenizer/",
            },
        }
        with open(os.path.join(directory, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"[HajeenExporter] Full export complete: {os.path.abspath(directory)}/")
        return os.path.abspath(directory)
