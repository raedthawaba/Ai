from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dpo_trainer import DPOConfig, DPOTrainerWrapper
from .evaluation_system import AlignmentEvaluator
from .preference_dataset import PreferenceDatasetBuilder
from .ppo_trainer import PPOConfig, PPOTrainerWrapper
from .reward_model import RewardModelPipeline

logger = logging.getLogger(__name__)


class AlignmentPipeline:
    """
    Full orchestrator for the Alignment Layer.
    Supports:
    - Preference dataset construction
    - DPO training (Direct Preference Optimisation)
    - PPO / RLHF training
    - Alignment evaluation
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.dataset_builder = PreferenceDatasetBuilder(
            output_path=self.config.get("dataset_dir", "storage_data/alignment/datasets")
        )
        self.reward_model = RewardModelPipeline(
            model_name_or_path=self.config.get("reward_model_path"),
            device=self.config.get("device", "cuda"),
        )
        self.evaluator = AlignmentEvaluator()
        logger.info("AlignmentPipeline initialised.")

    # ── Dataset ──────────────────────────────────────────────────────────

    def build_preference_dataset(
        self, raw_data: List[Dict[str, str]], output_file: str
    ) -> str:
        """
        Build and persist a JSONL preference dataset.

        raw_data items must have keys: prompt, chosen, rejected
        Returns the path to the saved file.
        """
        self.dataset_builder.clear()
        for item in raw_data:
            self.dataset_builder.add_example(
                prompt=item["prompt"],
                chosen=item["chosen"],
                rejected=item["rejected"],
            )
        path = self.dataset_builder.save(output_file)
        logger.info("Preference dataset saved to %s (%d examples).", path, len(raw_data))
        return path

    # ── DPO ─────────────────────────────────────────────────────────────

    def run_dpo_alignment(
        self,
        dpo_config: DPOConfig,
        model: Any,
        tokenizer: Any,
        train_dataset: Any,
        ref_model: Optional[Any] = None,
        eval_dataset: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full DPO training run.

        Parameters
        ----------
        dpo_config   : DPOConfig instance (model path, lr, epochs, …)
        model        : HuggingFace AutoModelForCausalLM (loaded externally)
        tokenizer    : HuggingFace tokenizer
        train_dataset: HuggingFace Dataset with columns: prompt, chosen, rejected
        ref_model    : optional reference model (defaults to frozen copy of model)
        eval_dataset : optional validation split
        """
        logger.info(
            "Starting DPO alignment — model=%s epochs=%d",
            dpo_config.model_name_or_path,
            dpo_config.num_train_epochs,
        )
        trainer = DPOTrainerWrapper(dpo_config)
        trainer.setup(
            model=model,
            ref_model=ref_model,
            tokenizer=tokenizer,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
        )
        metrics = trainer.train()
        saved_path = trainer.save()
        logger.info("DPO alignment complete. Metrics: %s", metrics)
        return {
            "status": "completed",
            "metrics": metrics,
            "model_path": saved_path,
            "config": dpo_config.__dict__,
        }

    # ── PPO / RLHF ───────────────────────────────────────────────────────

    def run_ppo_alignment(
        self,
        ppo_config: PPOConfig,
        model: Any,
        tokenizer: Any,
        dataset: Any,
        reward_model_pipeline: Optional[Any] = None,
        ref_model: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full PPO / RLHF training run.

        reward_model_pipeline must expose .batch_score(queries, responses) -> List[float].
        If not provided, uses self.reward_model (loaded separately).
        """
        logger.info(
            "Starting PPO alignment — model=%s batch=%d",
            ppo_config.model_name,
            ppo_config.batch_size,
        )
        trainer = PPOTrainerWrapper(ppo_config)
        trainer.setup(
            model=model,
            ref_model=ref_model,
            tokenizer=tokenizer,
            dataset=dataset,
        )
        reward_pipeline = reward_model_pipeline or self.reward_model
        trainer.train(reward_model_pipeline=reward_pipeline)
        logger.info("PPO alignment complete.")
        return {
            "status": "completed",
            "model_path": ppo_config.output_dir,
            "config": ppo_config.__dict__,
        }

    # ── Evaluation ───────────────────────────────────────────────────────

    def evaluate_alignment(
        self,
        prompt: str,
        response: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate a single response for alignment quality."""
        return self.evaluator.run_full_eval(prompt, response, context)

    def batch_evaluate(
        self, samples: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Evaluate a list of {prompt, response} dicts."""
        results = []
        for sample in samples:
            result = self.evaluator.run_full_eval(
                sample["prompt"],
                sample["response"],
                sample.get("context"),
            )
            results.append(result)
        avg_score = (
            sum(r.get("overall_score", 0) for r in results) / len(results)
            if results
            else 0.0
        )
        logger.info(
            "Batch evaluation complete — %d samples, avg score=%.3f",
            len(results),
            avg_score,
        )
        return results

    # ── Reward Scoring ───────────────────────────────────────────────────

    def score_responses(
        self, prompt: str, responses: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Score a list of candidate responses using the reward model.
        Requires reward model to be loaded first (self.reward_model.load_model()).
        """
        scored = []
        for resp in responses:
            reward = self.reward_model.score_response(prompt, resp)
            scored.append({"response": resp, "reward_score": reward.score})
        scored.sort(key=lambda x: x["reward_score"], reverse=True)
        return scored
