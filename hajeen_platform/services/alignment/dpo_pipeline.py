from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DPOPipeline:
    """
    Direct Preference Optimisation (DPO) pipeline.
    Wraps the TRL DPOTrainer for alignment training from preference data.
    """

    def __init__(
        self,
        model: Any,
        ref_model: Optional[Any],
        tokenizer: Any,
        output_dir: str = "storage_data/dpo_output",
        beta: float = 0.1,
        learning_rate: float = 5e-7,
        num_train_epochs: int = 3,
        per_device_batch_size: int = 1,
        gradient_accumulation_steps: int = 4,
        max_length: int = 1024,
        max_prompt_length: int = 512,
    ) -> None:
        self.model = model
        self.ref_model = ref_model
        self.tokenizer = tokenizer
        self.output_dir = output_dir
        self.beta = beta
        self.learning_rate = learning_rate
        self.num_train_epochs = num_train_epochs
        self.per_device_batch_size = per_device_batch_size
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.max_length = max_length
        self.max_prompt_length = max_prompt_length
        self._trainer: Optional[Any] = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        logger.info("DPOPipeline initialised (beta=%.2f, lr=%s).", beta, learning_rate)

    def prepare_preference_data(
        self, preferences: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, str]]:
        """Convert raw preference dicts to (prompt, chosen, rejected) tuples."""
        processed = []
        for p in preferences:
            prompt = p.get("prompt", "")
            chosen = p.get("chosen_response", p.get("chosen", ""))
            rejected = p.get("rejected_response", p.get("rejected", ""))
            if prompt and chosen and rejected:
                processed.append((prompt, chosen, rejected))
            else:
                logger.warning("Skipping incomplete preference sample: %s", str(p)[:80])
        logger.info("Prepared %d preference samples.", len(processed))
        return processed

    def setup_trainer(self, train_dataset: Any, eval_dataset: Optional[Any] = None) -> None:
        """Initialise the TRL DPOTrainer with the configured model and settings."""
        try:
            from trl import DPOTrainer
            from transformers import TrainingArguments

            args = TrainingArguments(
                output_dir=self.output_dir,
                learning_rate=self.learning_rate,
                num_train_epochs=self.num_train_epochs,
                per_device_train_batch_size=self.per_device_batch_size,
                gradient_accumulation_steps=self.gradient_accumulation_steps,
                evaluation_strategy="steps" if eval_dataset else "no",
                save_steps=500,
                logging_steps=10,
                report_to=[],
                remove_unused_columns=False,
            )
            self._trainer = DPOTrainer(
                model=self.model,
                ref_model=self.ref_model,
                args=args,
                beta=self.beta,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                tokenizer=self.tokenizer,
                max_length=self.max_length,
                max_prompt_length=self.max_prompt_length,
            )
            logger.info("DPO trainer ready.")
        except ImportError:
            logger.error("trl is not installed. Run: pip install trl")
            raise

    def train(self) -> Dict[str, Any]:
        """Execute DPO training and return metrics."""
        if self._trainer is None:
            raise RuntimeError("Call setup_trainer() before train().")
        logger.info("Starting DPO training…")
        result = self._trainer.train()
        metrics = result.metrics if hasattr(result, "metrics") else {}
        self._trainer.save_model(self.output_dir)
        logger.info("DPO training complete. Metrics: %s", metrics)
        return {"status": "completed", "metrics": metrics, "output_dir": self.output_dir}

    async def run_pipeline(
        self,
        preferences: List[Dict[str, Any]],
        epochs: int = 1,
        eval_split: float = 0.1,
    ) -> Dict[str, Any]:
        """High-level async entry point: prepare data → setup → train."""
        try:
            from datasets import Dataset
        except ImportError:
            logger.error("datasets is not installed. Run: pip install datasets")
            raise

        processed = self.prepare_preference_data(preferences)
        if not processed:
            return {"status": "error", "reason": "No valid preference samples."}

        records = [{"prompt": p, "chosen": c, "rejected": r} for p, c, r in processed]
        hf_dataset = Dataset.from_list(records)

        split = hf_dataset.train_test_split(test_size=eval_split) if eval_split > 0 else None
        train_ds = split["train"] if split else hf_dataset
        eval_ds = split["test"] if split else None

        self.num_train_epochs = epochs
        self.setup_trainer(train_ds, eval_ds)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.train)
        return result
