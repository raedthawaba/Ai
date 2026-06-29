from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from .preference_dataset import PreferenceDatasetBuilder
from .reward_model import RewardModelPipeline
from .dpo_trainer import DPOTrainerWrapper, DPOConfig
from .ppo_trainer import PPOTrainerWrapper, PPOConfig
from .evaluation_system import AlignmentEvaluator

logger = logging.getLogger(__name__)

class AlignmentPipeline:
    """Orchestrator for the Alignment Layer pipeline."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.dataset_builder = PreferenceDatasetBuilder()
        self.reward_model = RewardModelPipeline(self.config.get("reward_model_path"))
        self.evaluator = AlignmentEvaluator()

    def build_preference_dataset(self, raw_data: List[Dict[str, str]], output_file: str) -> str:
        """Build a preference dataset from raw prompt/chosen/rejected data."""
        self.dataset_builder.clear()
        for item in raw_data:
            self.dataset_builder.add_example(
                prompt=item["prompt"],
                chosen=item["chosen"],
                rejected=item["rejected"]
            )
        return self.dataset_builder.save(output_file)

    def run_dpo_alignment(self, dpo_config: DPOConfig, train_dataset: Any) -> Dict[str, Any]:
        """Run the DPO alignment process."""
        trainer = DPOTrainerWrapper(dpo_config)
        # Note: In a real scenario, model/tokenizer would be passed here
        # This is a high-level orchestration method
        logger.info("DPO alignment process initiated via pipeline")
        return {"status": "initiated", "config": dpo_config}

    def run_ppo_alignment(self, ppo_config: PPOConfig, dataset: Any) -> Dict[str, Any]:
        """Run the PPO alignment process."""
        trainer = PPOTrainerWrapper(ppo_config)
        # Note: Model and Tokenizer would be loaded and passed here in a full execution
        logger.info("PPO alignment process initiated via pipeline")
        return {"status": "initiated", "config": ppo_config}

    def evaluate_alignment(self, prompt: str, response: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate a response's alignment."""
        return self.evaluator.run_full_eval(prompt, response, context)
