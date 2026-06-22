from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .trainer import TrainingConfig
from .dataset_loader import DatasetLoader
from .checkpoint_manager import CheckpointManager
from .metrics import TrainingMetrics
from .lora_trainer import LoRATrainer, LoRAConfig

logger = logging.getLogger(__name__)


class FineTuner:
    """End-to-end fine-tuning orchestrator combining all training components."""

    def __init__(
        self,
        base_model_id: str,
        output_dir: str = "storage_data/finetuned",
        use_lora: bool = True,
        lora_config: Optional[LoRAConfig] = None,
        training_config: Optional[TrainingConfig] = None,
    ) -> None:
        self.base_model_id = base_model_id
        self.output_dir = output_dir
        self.use_lora = use_lora
        self.lora_config = lora_config or LoRAConfig()
        self.training_config = training_config or TrainingConfig(output_dir=output_dir)
        self.metrics = TrainingMetrics()
        self.checkpoint_manager = CheckpointManager(f"{output_dir}/checkpoints")
        self.dataset_loader = DatasetLoader()
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def load_base_model(self) -> tuple[Any, Any]:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
            import torch  # type: ignore

            tokenizer = AutoTokenizer.from_pretrained(self.base_model_id, use_fast=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            model = AutoModelForCausalLM.from_pretrained(
                self.base_model_id,
                torch_dtype=torch.float16,
                device_map="auto",
            )
            logger.info("Base model loaded: %s", self.base_model_id)
            return model, tokenizer
        except ImportError as exc:
            raise RuntimeError("transformers + torch required") from exc

    def prepare_dataset(
        self,
        data_path: str,
        tokenizer: Any,
        text_field: str = "text",
        max_length: int = 2048,
    ) -> Any:
        records = self.dataset_loader.load_jsonl(data_path)
        texts = [r.get(text_field, "") for r in records if r.get(text_field)]

        try:
            from datasets import Dataset  # type: ignore

            ds = Dataset.from_dict({"text": texts})

            def tokenize(batch: Dict) -> Dict:
                return tokenizer(
                    batch["text"],
                    truncation=True,
                    max_length=max_length,
                    padding="max_length",
                )

            return ds.map(tokenize, batched=True, remove_columns=["text"])
        except ImportError as exc:
            raise RuntimeError("datasets library required") from exc

    def run(
        self,
        train_data_path: str,
        eval_data_path: Optional[str] = None,
        text_field: str = "text",
    ) -> Dict:
        self.metrics.start()
        logger.info("Starting fine-tuning: %s", self.base_model_id)

        model, tokenizer = self.load_base_model()
        train_ds = self.prepare_dataset(train_data_path, tokenizer, text_field)
        eval_ds = None
        if eval_data_path:
            eval_ds = self.prepare_dataset(eval_data_path, tokenizer, text_field)

        try:
            from transformers import DataCollatorForLanguageModeling  # type: ignore
            collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
        except ImportError:
            collator = None

        if self.use_lora:
            trainer = LoRATrainer(self.training_config, self.lora_config)
            trainer.setup(model, tokenizer, train_ds, eval_ds, collator)
            train_metrics = trainer.train()
            trainer.save_lora_weights(f"{self.output_dir}/lora_weights")
        else:
            from .trainer import Trainer
            trainer_obj = Trainer(self.training_config)
            trainer_obj.setup(model, tokenizer, train_ds, eval_ds, collator)
            train_metrics = trainer_obj.train()
            trainer_obj.save(self.output_dir)

        result = {**train_metrics, "metrics": self.metrics.summary()}
        logger.info("Fine-tuning complete: %s", result)
        return result
