from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .trainer import Trainer, TrainingConfig

logger = logging.getLogger(__name__)


@dataclass
class LoRAConfig:
    r: int = 16
    lora_alpha: int = 32
    target_modules: List[str] = None  # type: ignore
    lora_dropout: float = 0.05
    bias: str = "none"
    task_type: str = "CAUSAL_LM"

    def __post_init__(self) -> None:
        if self.target_modules is None:
            self.target_modules = ["q_proj", "v_proj", "k_proj", "o_proj"]


class LoRATrainer:
    """Fine-tune a model using LoRA (Low-Rank Adaptation) via PEFT."""

    def __init__(
        self,
        training_config: TrainingConfig,
        lora_config: Optional[LoRAConfig] = None,
    ) -> None:
        self.training_config = training_config
        self.lora_config = lora_config or LoRAConfig()
        self._trainer = Trainer(training_config)
        self._peft_model: Optional[Any] = None

    def apply_lora(self, model: Any) -> Any:
        try:
            from peft import LoraConfig, get_peft_model, TaskType  # type: ignore

            cfg = LoraConfig(
                r=self.lora_config.r,
                lora_alpha=self.lora_config.lora_alpha,
                target_modules=self.lora_config.target_modules,
                lora_dropout=self.lora_config.lora_dropout,
                bias=self.lora_config.bias,
                task_type=TaskType.CAUSAL_LM,
            )
            peft_model = get_peft_model(model, cfg)
            peft_model.print_trainable_parameters()
            self._peft_model = peft_model
            logger.info("LoRA applied: r=%d, alpha=%d", self.lora_config.r, self.lora_config.lora_alpha)
            return peft_model
        except ImportError as exc:
            raise RuntimeError("peft library required for LoRA training") from exc

    def setup(
        self,
        model: Any,
        tokenizer: Any,
        train_dataset: Any,
        eval_dataset: Optional[Any] = None,
        data_collator: Optional[Any] = None,
    ) -> None:
        peft_model = self.apply_lora(model)
        self._trainer.setup(peft_model, tokenizer, train_dataset, eval_dataset, data_collator)

    def train(self, resume: bool = False) -> Dict:
        return self._trainer.train(resume=resume)

    def evaluate(self) -> Dict:
        return self._trainer.evaluate()

    def save_lora_weights(self, path: str) -> str:
        if self._peft_model is None:
            raise RuntimeError("No LoRA model to save")
        self._peft_model.save_pretrained(path)
        logger.info("LoRA weights saved: %s", path)
        return path

    def merge_and_save(self, path: str) -> str:
        """Merge LoRA weights into base model and save."""
        if self._peft_model is None:
            raise RuntimeError("No LoRA model to merge")
        try:
            merged = self._peft_model.merge_and_unload()
            merged.save_pretrained(path)
            logger.info("Merged model saved: %s", path)
            return path
        except Exception as exc:
            raise RuntimeError(f"Failed to merge LoRA weights: {exc}") from exc
