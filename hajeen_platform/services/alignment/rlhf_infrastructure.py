from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RLHFInfrastructure:
    """
    Reinforcement Learning from Human Feedback (RLHF) infrastructure.
    Coordinates:
    1. Human feedback collection / simulation
    2. Reward model training
    3. PPO fine-tuning of the policy model
    """

    def __init__(
        self,
        policy_model: Any,
        reward_model: Any,
        tokenizer: Any,
        output_dir: str = "storage_data/rlhf_output",
        ppo_batch_size: int = 64,
        ppo_mini_batch: int = 4,
        ppo_epochs: int = 4,
        learning_rate: float = 1.41e-5,
        target_kl: float = 0.1,
    ) -> None:
        self.policy_model = policy_model
        self.reward_model = reward_model
        self.tokenizer = tokenizer
        self.output_dir = output_dir
        self.ppo_batch_size = ppo_batch_size
        self.ppo_mini_batch = ppo_mini_batch
        self.ppo_epochs = ppo_epochs
        self.learning_rate = learning_rate
        self.target_kl = target_kl
        self._ppo_trainer: Optional[Any] = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        logger.info("RLHFInfrastructure initialised.")

    # ── Feedback Collection ───────────────────────────────────────────────

    async def collect_human_feedback(
        self, prompts: List[str], generate_fn: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Collect (or simulate) human preference feedback for a list of prompts.
        In production, replace this with a real annotation interface.
        If generate_fn is provided, it is used to generate candidate responses.
        """
        logger.info("Collecting human feedback for %d prompts.", len(prompts))
        feedback: List[Dict[str, Any]] = []
        for i, prompt in enumerate(prompts):
            if generate_fn:
                try:
                    resp_a = await generate_fn(prompt + " [variation A]")
                    resp_b = await generate_fn(prompt + " [variation B]")
                except Exception as exc:
                    logger.warning("generate_fn failed for prompt %d: %s", i, exc)
                    resp_a = f"Response A for prompt {i}"
                    resp_b = f"Response B for prompt {i}"
            else:
                resp_a = f"Response A for: {prompt[:60]}"
                resp_b = f"Response B for: {prompt[:60]}"

            feedback.append({
                "prompt": prompt,
                "chosen_response": resp_a,
                "rejected_response": resp_b,
            })
        logger.info("Collected %d feedback samples.", len(feedback))
        return feedback

    # ── Reward Model Training ─────────────────────────────────────────────

    def setup_reward_model_trainer(
        self, train_dataset: Any, eval_dataset: Optional[Any] = None
    ) -> None:
        """Set up TRL RewardTrainer for training the reward model."""
        try:
            from trl import RewardTrainer, RewardConfig

            config = RewardConfig(
                output_dir=f"{self.output_dir}/reward_model",
                per_device_train_batch_size=4,
                num_train_epochs=1,
                learning_rate=self.learning_rate,
                remove_unused_columns=False,
                logging_steps=10,
            )
            from trl import RewardTrainer
            self._reward_trainer = RewardTrainer(
                model=self.reward_model,
                tokenizer=self.tokenizer,
                args=config,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
            )
            logger.info("Reward model trainer ready.")
        except ImportError:
            logger.error("trl not installed — run: pip install trl")
            raise

    def train_reward_model(self) -> Dict[str, Any]:
        """Run reward model training."""
        if not hasattr(self, "_reward_trainer") or self._reward_trainer is None:
            raise RuntimeError("Call setup_reward_model_trainer() first.")
        logger.info("Training reward model…")
        result = self._reward_trainer.train()
        metrics = result.metrics if hasattr(result, "metrics") else {}
        logger.info("Reward model training complete. Metrics: %s", metrics)
        return metrics

    # ── PPO Training ──────────────────────────────────────────────────────

    def setup_ppo_trainer(self, dataset: Optional[Any] = None) -> None:
        """Initialise TRL PPOTrainer for policy optimisation."""
        try:
            from trl import PPOTrainer, PPOConfig as TRLPPOConfig, create_reference_model

            ppo_config = TRLPPOConfig(
                learning_rate=self.learning_rate,
                batch_size=self.ppo_batch_size,
                mini_batch_size=self.ppo_mini_batch,
                ppo_epochs=self.ppo_epochs,
                target_kl=self.target_kl,
                optimize_cuda_cache=True,
            )
            ref_model = create_reference_model(self.policy_model)
            self._ppo_trainer = PPOTrainer(
                config=ppo_config,
                model=self.policy_model,
                ref_model=ref_model,
                tokenizer=self.tokenizer,
                dataset=dataset,
            )
            logger.info("PPO trainer ready.")
        except ImportError:
            logger.error("trl not installed — run: pip install trl")
            raise

    async def run_ppo_step(
        self, prompt: str, generated_response: str
    ) -> Dict[str, Any]:
        """Execute a single PPO optimisation step."""
        if self._ppo_trainer is None:
            raise RuntimeError("Call setup_ppo_trainer() first.")
        try:
            import torch
            query_ids = self.tokenizer.encode(prompt, return_tensors="pt").squeeze()
            response_ids = self.tokenizer.encode(generated_response, return_tensors="pt").squeeze()
            reward = self.reward_model(
                self.tokenizer(prompt + generated_response, return_tensors="pt")["input_ids"]
            )
            reward_tensor = torch.tensor([float(reward)])
            stats = self._ppo_trainer.step([query_ids], [response_ids], [reward_tensor])
            return {"success": True, "ppo_loss": stats.get("ppo/loss/total", 0.0),
                    "kl_divergence": stats.get("ppo/mean_non_score_reward", 0.0)}
        except Exception as exc:
            logger.error("PPO step failed: %s", exc)
            return {"success": False, "error": str(exc)}

    # ── Full Pipeline ─────────────────────────────────────────────────────

    async def run_rlhf_pipeline(
        self,
        initial_prompts: List[str],
        reward_model_epochs: int = 1,
        ppo_steps: int = 5,
        generate_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """End-to-end RLHF: feedback → reward training → PPO."""
        # 1. Collect feedback
        feedback = await self.collect_human_feedback(initial_prompts, generate_fn)

        # 2. Build reward training dataset
        try:
            from datasets import Dataset as HFDataset
            reward_ds = HFDataset.from_list([
                {"prompt": f["prompt"], "chosen": f["chosen_response"], "rejected": f["rejected_response"]}
                for f in feedback
            ])
            split = reward_ds.train_test_split(test_size=0.1)
            self.setup_reward_model_trainer(split["train"], split["test"])
            loop = asyncio.get_event_loop()
            reward_metrics = await loop.run_in_executor(None, self.train_reward_model)
        except ImportError:
            logger.warning("datasets not installed — skipping reward model training.")
            reward_metrics = {}

        # 3. Run PPO steps
        self.setup_ppo_trainer()
        ppo_losses = []
        for step in range(ppo_steps):
            for prompt in initial_prompts:
                response = f"[PPO step {step}] Response to: {prompt[:40]}"
                result = await self.run_ppo_step(prompt, response)
                if result.get("success"):
                    ppo_losses.append(result.get("ppo_loss", 0.0))

        avg_ppo_loss = sum(ppo_losses) / len(ppo_losses) if ppo_losses else 0.0
        logger.info("RLHF pipeline complete. avg_ppo_loss=%.4f", avg_ppo_loss)
        return {
            "status": "completed",
            "reward_model_metrics": reward_metrics,
            "average_ppo_loss": avg_ppo_loss,
            "ppo_steps_run": len(ppo_losses),
        }
