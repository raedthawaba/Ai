"""
training_pipeline.py — Full training pipeline for Hajeen Foundation Model.

Features:
    - Mixed precision training (FP16 / BF16)
    - Gradient accumulation
    - Learning rate scheduling (cosine with warmup)
    - Gradient clipping
    - Checkpoint saving and resuming
    - Distributed training ready (DDP)
    - Logging: loss, perplexity, learning rate

Usage:
    config = TrainingConfig(max_steps=10000, batch_size=8)
    pipeline = TrainingPipeline(model, tokenizer, train_ds, val_ds, config)
    pipeline.train()
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import torch
import torch.nn as nn
from torch.cuda.amp import GradScaler, autocast
from torch.optim import AdamW
from torch.utils.data import DataLoader


@dataclass
class TrainingConfig:
    """Configuration for the Hajeen training pipeline."""

    # ── Output ────────────────────────────────────────────────────────────
    output_dir: str = "outputs/hajeen_training"

    # ── Batching ──────────────────────────────────────────────────────────
    batch_size: int = 8
    gradient_accumulation_steps: int = 4

    # ── Steps / Epochs ────────────────────────────────────────────────────
    max_steps: int = 100_000
    max_epochs: Optional[int] = None      # If set, overrides max_steps

    # ── Optimizer ─────────────────────────────────────────────────────────
    learning_rate: float = 3e-4
    weight_decay: float = 0.1
    beta1: float = 0.9
    beta2: float = 0.95
    eps: float = 1e-8
    max_grad_norm: float = 1.0

    # ── LR Schedule ───────────────────────────────────────────────────────
    warmup_steps: int = 1_000
    lr_schedule: str = "cosine"           # "cosine" | "linear" | "constant"
    min_lr_ratio: float = 0.1             # Minimum LR = learning_rate * min_lr_ratio

    # ── Mixed Precision ───────────────────────────────────────────────────
    use_amp: bool = True
    amp_dtype: str = "float16"            # "float16" | "bfloat16"

    # ── Checkpoint ────────────────────────────────────────────────────────
    save_every_n_steps: int = 1_000
    keep_n_checkpoints: int = 3

    # ── Evaluation ────────────────────────────────────────────────────────
    eval_every_n_steps: int = 500
    eval_max_batches: int = 50

    # ── Logging ───────────────────────────────────────────────────────────
    log_every_n_steps: int = 10

    # ── DataLoader ────────────────────────────────────────────────────────
    num_workers: int = 0
    seed: int = 42


def _cosine_lr(
    step: int,
    warmup_steps: int,
    max_steps: int,
    max_lr: float,
    min_lr: float,
) -> float:
    if step < warmup_steps:
        return max_lr * (step / max(1, warmup_steps))
    progress = (step - warmup_steps) / max(1, max_steps - warmup_steps)
    cosine = 0.5 * (1 + math.cos(math.pi * progress))
    return min_lr + (max_lr - min_lr) * cosine


def _linear_lr(step: int, warmup_steps: int, max_steps: int, max_lr: float, min_lr: float) -> float:
    if step < warmup_steps:
        return max_lr * (step / max(1, warmup_steps))
    progress = (step - warmup_steps) / max(1, max_steps - warmup_steps)
    return max_lr - (max_lr - min_lr) * progress


class TrainingPipeline:
    """
    End-to-end training pipeline for HajeenForCausalLM.

    Handles:
        - DataLoader setup
        - Optimizer and LR scheduler
        - Mixed precision (AMP)
        - Gradient accumulation
        - Checkpoint save / resume
        - Evaluation loop
        - Logging

    Args:
        model: HajeenForCausalLM instance.
        tokenizer: HajeenTokenizer instance.
        train_dataset: Training dataset.
        val_dataset: Validation dataset (optional).
        config: TrainingConfig.
    """

    def __init__(
        self,
        model: nn.Module,
        tokenizer,
        train_dataset,
        val_dataset=None,
        config: Optional[TrainingConfig] = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.config = config or TrainingConfig()

        # Device
        self.device = (
            torch.device("cuda") if torch.cuda.is_available()
            else torch.device("mps") if torch.backends.mps.is_available()
            else torch.device("cpu")
        )
        self.model.to(self.device)

        # Optimizer
        self.optimizer = self._build_optimizer()

        # Scaler for mixed precision
        self.scaler = GradScaler(enabled=self.config.use_amp and self.device.type == "cuda")

        # AMP context dtype
        if self.config.amp_dtype == "bfloat16":
            self._amp_dtype = torch.bfloat16
        else:
            self._amp_dtype = torch.float16

        # State
        self.global_step: int = 0
        self.epoch: int = 0
        self._checkpoint_manager = None
        os.makedirs(self.config.output_dir, exist_ok=True)

    def _build_optimizer(self) -> AdamW:
        """Build AdamW with weight decay applied only to weight matrices."""
        decay_params = []
        no_decay_params = []
        for name, param in self.model.named_parameters():
            if not param.requires_grad:
                continue
            if "bias" in name or "norm" in name or "embedding" in name:
                no_decay_params.append(param)
            else:
                decay_params.append(param)

        return AdamW(
            [
                {"params": decay_params, "weight_decay": self.config.weight_decay},
                {"params": no_decay_params, "weight_decay": 0.0},
            ],
            lr=self.config.learning_rate,
            betas=(self.config.beta1, self.config.beta2),
            eps=self.config.eps,
        )

    def _get_lr(self) -> float:
        """Compute the current learning rate."""
        max_lr = self.config.learning_rate
        min_lr = max_lr * self.config.min_lr_ratio
        max_steps = self.config.max_steps

        if self.config.lr_schedule == "cosine":
            return _cosine_lr(self.global_step, self.config.warmup_steps, max_steps, max_lr, min_lr)
        elif self.config.lr_schedule == "linear":
            return _linear_lr(self.global_step, self.config.warmup_steps, max_steps, max_lr, min_lr)
        else:
            return max_lr

    def _set_lr(self, lr: float) -> None:
        for pg in self.optimizer.param_groups:
            pg["lr"] = lr

    def _train_step(self, batch: dict) -> float:
        """Execute a single forward + backward step. Return loss value."""
        input_ids = batch["input_ids"].to(self.device)
        labels    = batch["labels"].to(self.device)

        use_amp = self.config.use_amp and self.device.type == "cuda"

        with autocast(device_type=self.device.type, dtype=self._amp_dtype, enabled=use_amp):
            out = self.model(input_ids=input_ids, labels=labels)
            loss = out["loss"] / self.config.gradient_accumulation_steps

        self.scaler.scale(loss).backward()
        return loss.item() * self.config.gradient_accumulation_steps

    def _optimizer_step(self) -> None:
        """Clip gradients, step optimizer, zero grads."""
        self.scaler.unscale_(self.optimizer)
        nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
        self.scaler.step(self.optimizer)
        self.scaler.update()
        self.optimizer.zero_grad(set_to_none=True)

    @torch.no_grad()
    def evaluate(self) -> dict:
        """Run evaluation on val_dataset. Returns dict with 'loss' and 'ppl'."""
        if self.val_dataset is None:
            return {}

        self.model.eval()
        from hajeen_model.datasets.dataset_builder import HajeenDataset
        loader = DataLoader(
            self.val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
            collate_fn=lambda b: HajeenDataset.collate_fn(b, pad_token_id=self.tokenizer.pad_token_id),
        )

        total_loss = 0.0
        n_batches = 0

        for batch in loader:
            if n_batches >= self.config.eval_max_batches:
                break
            input_ids = batch["input_ids"].to(self.device)
            labels    = batch["labels"].to(self.device)
            out = self.model(input_ids=input_ids, labels=labels)
            total_loss += out["loss"].item()
            n_batches += 1

        self.model.train()
        avg_loss = total_loss / max(1, n_batches)
        ppl = math.exp(min(avg_loss, 20))
        return {"val_loss": avg_loss, "val_ppl": ppl}

    def _save_checkpoint(self) -> None:
        """Save a training checkpoint."""
        from hajeen_model.checkpoints.checkpoint_manager import CheckpointManager
        if self._checkpoint_manager is None:
            self._checkpoint_manager = CheckpointManager(
                self.config.output_dir,
                keep_n=self.config.keep_n_checkpoints,
            )
        self._checkpoint_manager.save(
            model=self.model,
            optimizer=self.optimizer,
            scaler=self.scaler,
            step=self.global_step,
            epoch=self.epoch,
        )

    def resume_from_checkpoint(self, checkpoint_dir: str) -> None:
        """Resume training from a saved checkpoint."""
        from hajeen_model.checkpoints.checkpoint_manager import CheckpointManager
        mgr = CheckpointManager(checkpoint_dir)
        state = mgr.load_latest(self.model, self.optimizer, self.scaler)
        if state:
            self.global_step = state.get("step", 0)
            self.epoch = state.get("epoch", 0)
            print(f"[TrainingPipeline] Resumed from step {self.global_step}")

    # ── Main training loop ────────────────────────────────────────────────

    def train(self) -> None:
        """
        Run the full training loop.

        Logs to stdout. Saves checkpoints to config.output_dir.
        """
        from hajeen_model.datasets.dataset_builder import HajeenDataset

        print("=" * 60)
        print("  Hajeen Foundation Model — Training Pipeline")
        print("=" * 60)
        print(f"  Device   : {self.device}")
        print(f"  Model    : {self.model.num_parameters() / 1e6:.1f}M params")
        print(f"  Max steps: {self.config.max_steps}")
        print(f"  Batch    : {self.config.batch_size} × {self.config.gradient_accumulation_steps} accum")
        print(f"  LR       : {self.config.learning_rate} ({self.config.lr_schedule})")
        print(f"  AMP      : {self.config.use_amp} ({self.config.amp_dtype})")
        print()

        loader = DataLoader(
            self.train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            num_workers=self.config.num_workers,
            collate_fn=lambda b: HajeenDataset.collate_fn(b, pad_token_id=self.tokenizer.pad_token_id),
            pin_memory=self.device.type == "cuda",
            drop_last=True,
        )

        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)

        accum_loss = 0.0
        t0 = time.time()
        done = False

        while not done:
            self.epoch += 1
            for batch in loader:
                if self.global_step >= self.config.max_steps:
                    done = True
                    break

                # Update LR
                lr = self._get_lr()
                self._set_lr(lr)

                # Forward + backward
                loss_val = self._train_step(batch)
                accum_loss += loss_val

                # Optimizer step every gradient_accumulation_steps
                if (self.global_step + 1) % self.config.gradient_accumulation_steps == 0:
                    self._optimizer_step()

                self.global_step += 1

                # Logging
                if self.global_step % self.config.log_every_n_steps == 0:
                    elapsed = time.time() - t0
                    tps = self.global_step / elapsed
                    ppl = math.exp(min(accum_loss / self.config.log_every_n_steps, 20))
                    print(
                        f"  step={self.global_step:>7} "
                        f"loss={accum_loss / self.config.log_every_n_steps:.4f} "
                        f"ppl={ppl:.2f} "
                        f"lr={lr:.2e} "
                        f"steps/s={tps:.1f}"
                    )
                    accum_loss = 0.0

                # Evaluation
                if self.global_step % self.config.eval_every_n_steps == 0:
                    metrics = self.evaluate()
                    if metrics:
                        print(
                            f"  [EVAL] step={self.global_step} "
                            f"val_loss={metrics['val_loss']:.4f} "
                            f"val_ppl={metrics['val_ppl']:.2f}"
                        )

                # Checkpoint
                if self.global_step % self.config.save_every_n_steps == 0:
                    self._save_checkpoint()

            if self.config.max_epochs and self.epoch >= self.config.max_epochs:
                done = True

        # Final save
        self._save_checkpoint()
        print(f"\n[TrainingPipeline] Training complete at step {self.global_step}.")
        print(f"  Checkpoints saved in: {self.config.output_dir}")
