from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class DPOConfig:
    model_name_or_path: str
    output_dir: str = "storage_data/alignment/dpo_output"
    beta: float = 0.1
    learning_rate: float = 5e-7
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 4
    max_length: int = 1024
    max_prompt_length: int = 512
    warmup_steps: int = 100
    logging_steps: int = 10
    save_steps: int = 500
    eval_steps: int = 500
    report_to: List[str] = field(default_factory=list)

class DPOTrainerWrapper:
    """Wrapper for DPO (Direct Preference Optimization) training."""

    def __init__(self, config: DPOConfig) -> None:
        self.config = config
        self._trainer = None
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

    def setup(self, model: Any, ref_model: Optional[Any], tokenizer: Any, train_dataset: Any, eval_dataset: Optional[Any] = None) -> None:
        """Setup the DPOTrainer from TRL library."""
        try:
            from trl import DPOTrainer
            from transformers import TrainingArguments

            training_args = TrainingArguments(
                output_dir=self.config.output_dir,
                learning_rate=self.config.learning_rate,
                num_train_epochs=self.config.num_train_epochs,
                per_device_train_batch_size=self.config.per_device_train_batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                logging_steps=self.config.logging_steps,
                save_steps=self.config.save_steps,
                evaluation_strategy="steps" if eval_dataset else "no",
                eval_steps=self.config.eval_steps,
                report_to=self.config.report_to,
                remove_unused_columns=False,
            )

            self._trainer = DPOTrainer(
                model=model,
                ref_model=ref_model,
                args=training_args,
                beta=self.config.beta,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                tokenizer=tokenizer,
                max_length=self.config.max_length,
                max_prompt_length=self.config.max_prompt_length,
            )
            logger.info("DPO Trainer setup complete")
        except ImportError:
            logger.error("trl or transformers not installed. Please install them to use DPO.")
            raise

    def train(self) -> Dict[str, Any]:
        """Run DPO training."""
        if self._trainer is None:
            raise RuntimeError("DPO Trainer not set up. Call setup() first.")
        
        logger.info("Starting DPO training...")
        result = self._trainer.train()
        logger.info("DPO training complete")
        return result.metrics

    def save(self, path: Optional[str] = None) -> str:
        """Save the trained model."""
        if self._trainer is None:
            raise RuntimeError("DPO Trainer not set up.")
        
        out_path = path or self.config.output_dir
        self._trainer.save_model(out_path)
        logger.info(f"DPO model saved to {out_path}")
        return out_path
