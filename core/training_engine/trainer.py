from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    output_dir: str = "storage_data/training_output"
    num_epochs: int = 3
    per_device_train_batch_size: int = 4
    per_device_eval_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03
    lr_scheduler_type: str = "cosine"
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    logging_steps: int = 10
    eval_steps: int = 100
    save_steps: int = 200
    fp16: bool = True
    bf16: bool = False
    dataloader_num_workers: int = 0
    seed: int = 42
    max_seq_length: int = 2048
    report_to: List[str] = field(default_factory=list)
    resume_from_checkpoint: Optional[str] = None


class Trainer:
    """Generic trainer wrapper around HuggingFace Trainer."""

    def __init__(
        self,
        config: TrainingConfig,
        on_log: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        self.config = config
        self.on_log = on_log
        self._trainer: Optional[Any] = None
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

    def setup(
        self,
        model: Any,
        tokenizer: Any,
        train_dataset: Any,
        eval_dataset: Optional[Any] = None,
        data_collator: Optional[Any] = None,
    ) -> None:
        try:
            from transformers import TrainingArguments, Trainer as HFTrainer  # type: ignore

            args = TrainingArguments(
                output_dir=self.config.output_dir,
                num_train_epochs=self.config.num_epochs,
                per_device_train_batch_size=self.config.per_device_train_batch_size,
                per_device_eval_batch_size=self.config.per_device_eval_batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                learning_rate=self.config.learning_rate,
                warmup_ratio=self.config.warmup_ratio,
                lr_scheduler_type=self.config.lr_scheduler_type,
                weight_decay=self.config.weight_decay,
                max_grad_norm=self.config.max_grad_norm,
                logging_steps=self.config.logging_steps,
                eval_steps=self.config.eval_steps,
                save_steps=self.config.save_steps,
                fp16=self.config.fp16,
                bf16=self.config.bf16,
                seed=self.config.seed,
                report_to=self.config.report_to,
                evaluation_strategy="steps" if eval_dataset is not None else "no",
            )

            self._trainer = HFTrainer(
                model=model,
                args=args,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                tokenizer=tokenizer,
                data_collator=data_collator,
            )
            logger.info("Trainer setup complete")
        except ImportError as exc:
            raise RuntimeError("transformers not installed") from exc

    def train(self, resume: bool = False) -> Dict:
        if self._trainer is None:
            raise RuntimeError("Call setup() before train()")
        start = time.time()
        checkpoint = self.config.resume_from_checkpoint if resume else None
        result = self._trainer.train(resume_from_checkpoint=checkpoint)
        elapsed = time.time() - start
        metrics = dict(result.metrics) if hasattr(result, "metrics") else {}
        metrics["training_time_seconds"] = round(elapsed, 2)
        logger.info("Training complete: %s", metrics)
        return metrics

    def evaluate(self) -> Dict:
        if self._trainer is None:
            raise RuntimeError("Call setup() before evaluate()")
        return self._trainer.evaluate()

    def save(self, path: Optional[str] = None) -> str:
        if self._trainer is None:
            raise RuntimeError("Trainer not set up")
        out = path or self.config.output_dir
        self._trainer.save_model(out)
        logger.info("Model saved to: %s", out)
        return out
