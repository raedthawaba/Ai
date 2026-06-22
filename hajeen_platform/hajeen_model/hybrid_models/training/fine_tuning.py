"""
fine_tuning.py — Fine-tuning utilities for Hajeen Foundation Model.

Provides helpers for:
    - Freezing/unfreezing model parameters
    - Instruction-tuning data formatting
    - LoRA-style adapter injection (lightweight, no external deps)
    - RLHF reward signal stubs
"""

from __future__ import annotations

from typing import List, Optional, Set
import torch
import torch.nn as nn


# ── Parameter control ─────────────────────────────────────────────────────────

def freeze_all(model: nn.Module) -> None:
    """Freeze all model parameters."""
    for p in model.parameters():
        p.requires_grad_(False)


def unfreeze_all(model: nn.Module) -> None:
    """Unfreeze all model parameters."""
    for p in model.parameters():
        p.requires_grad_(True)


def freeze_except(model: nn.Module, keywords: List[str]) -> None:
    """
    Freeze all parameters EXCEPT those whose name contains any keyword.

    Common patterns:
        freeze_except(model, ["lm_head", "norm"])   # Only norms + head
        freeze_except(model, ["layers.23", "layers.24"])  # Last 2 layers
        freeze_except(model, ["lora"])  # Only LoRA adapters

    Args:
        model: The model to partially freeze.
        keywords: List of name substrings to keep trainable.
    """
    for name, param in model.named_parameters():
        trainable = any(kw in name for kw in keywords)
        param.requires_grad_(trainable)


def print_trainable_stats(model: nn.Module) -> None:
    """Print trainable vs total parameter counts."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    pct = trainable / max(total, 1) * 100
    print(
        f"[FineTuning] Trainable params: {trainable/1e6:.2f}M / "
        f"{total/1e6:.2f}M ({pct:.1f}%)"
    )


# ── LoRA adapter ──────────────────────────────────────────────────────────────

class LoRALinear(nn.Module):
    """
    LoRA (Low-Rank Adaptation) wrapper for nn.Linear.

    Adds two small trainable matrices A (d_in × r) and B (r × d_out)
    to a frozen linear layer:
        output = frozen_weight · x + alpha/r · (B · A · x)

    Only A and B are trained; the base weight stays frozen.

    Args:
        base_layer: The original nn.Linear to wrap.
        rank: LoRA rank (typically 4–64).
        alpha: Scaling factor (typically == rank).
    """

    def __init__(
        self,
        base_layer: nn.Linear,
        rank: int = 16,
        alpha: float = 16.0,
    ) -> None:
        super().__init__()
        self.base_layer = base_layer
        self.rank = rank
        self.alpha = alpha
        self.scaling = alpha / rank

        in_features = base_layer.in_features
        out_features = base_layer.out_features

        # Freeze base
        for p in base_layer.parameters():
            p.requires_grad_(False)

        # LoRA matrices
        self.lora_A = nn.Linear(in_features, rank, bias=False)
        self.lora_B = nn.Linear(rank, out_features, bias=False)

        # Initialize: A ~ N(0, 0.02), B = 0 → delta = 0 at init
        nn.init.normal_(self.lora_A.weight, std=0.02)
        nn.init.zeros_(self.lora_B.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base_out = self.base_layer(x)
        lora_out = self.lora_B(self.lora_A(x)) * self.scaling
        return base_out + lora_out

    def merge_weights(self) -> nn.Linear:
        """
        Merge LoRA weights into the base layer (for deployment).
        Returns a plain nn.Linear with merged weights.
        """
        merged = nn.Linear(
            self.base_layer.in_features,
            self.base_layer.out_features,
            bias=self.base_layer.bias is not None,
        )
        delta = (self.lora_B.weight @ self.lora_A.weight) * self.scaling
        merged.weight = nn.Parameter(self.base_layer.weight + delta)
        if self.base_layer.bias is not None:
            merged.bias = nn.Parameter(self.base_layer.bias.clone())
        return merged


def inject_lora(
    model: nn.Module,
    target_modules: List[str],
    rank: int = 16,
    alpha: float = 16.0,
) -> int:
    """
    Replace targeted nn.Linear layers with LoRALinear wrappers.

    Args:
        model: Model to modify in-place.
        target_modules: List of name substrings to target (e.g. ["q_proj", "v_proj"]).
        rank: LoRA rank.
        alpha: LoRA scaling.

    Returns:
        Number of layers replaced.
    """
    def _replace(parent: nn.Module, prefix: str) -> int:
        count = 0
        for name, child in list(parent.named_children()):
            full_name = f"{prefix}.{name}" if prefix else name
            if isinstance(child, nn.Linear) and any(t in full_name for t in target_modules):
                setattr(parent, name, LoRALinear(child, rank=rank, alpha=alpha))
                count += 1
            else:
                count += _replace(child, full_name)
        return count

    count = _replace(model, "")
    print(f"[LoRA] Injected {count} LoRA adapters (rank={rank}, alpha={alpha})")
    return count


# ── Instruction formatting ────────────────────────────────────────────────────

INSTRUCTION_TEMPLATE = """\
### Instruction:
{instruction}

### Response:
{response}"""

CHAT_TEMPLATE = """\
<|user|>
{user}
<|assistant|>
{assistant}"""


def format_instruction(instruction: str, response: str = "") -> str:
    """
    Format an instruction-response pair for fine-tuning.

    Args:
        instruction: The instruction/question.
        response: The expected response (empty during inference).
    """
    return INSTRUCTION_TEMPLATE.format(instruction=instruction, response=response)


def format_chat(user: str, assistant: str = "") -> str:
    """Format a chat-style turn."""
    return CHAT_TEMPLATE.format(user=user, assistant=assistant)


def build_instruction_dataset(
    pairs: List[dict],
    tokenizer,
    max_seq_len: int = 1024,
    response_key: str = "response",
    instruction_key: str = "instruction",
) -> List[dict]:
    """
    Tokenize instruction-response pairs.

    Labels for the instruction portion are set to -100 (ignored in loss),
    so the model only learns to predict the response.

    Args:
        pairs: List of dicts with instruction_key and response_key.
        tokenizer: HajeenTokenizer instance.
        max_seq_len: Maximum sequence length.
        response_key / instruction_key: Dict keys to use.

    Returns:
        List of {"input_ids": List[int], "labels": List[int]} dicts.
    """
    samples = []

    for pair in pairs:
        instruction = pair.get(instruction_key, "")
        response = pair.get(response_key, "")

        # Tokenize instruction (no BOS on response part)
        instr_text = f"### Instruction:\n{instruction}\n\n### Response:\n"
        instr_ids = tokenizer.encode(instr_text, add_bos=True)
        resp_ids  = tokenizer.encode(response, add_eos=True)

        input_ids = (instr_ids + resp_ids)[:max_seq_len]
        labels = ([-100] * len(instr_ids) + resp_ids)[:max_seq_len]

        samples.append({"input_ids": input_ids, "labels": labels})

    return samples
