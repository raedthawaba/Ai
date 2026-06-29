from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
import torch
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class PPOConfig:
    """Configuration for PPO training."""
    model_name: str
    reward_model_name: str
    output_dir: str = "storage_data/ppo_output"
    learning_rate: float = 1.41e-5
    batch_size: int = 64
    mini_batch_size: int = 4
    gradient_accumulation_steps: int = 1
    optimize_cuda_cache: bool = True
    early_stopping: bool = False
    target_kl: float = 0.1
    ppo_epochs: int = 4
    seed: int = 42
    max_length: int = 512

class PPOTrainerWrapper:
    """
    Wrapper for RLHF PPO Training using TRL (Transformer Reinforcement Learning).
    """
    def __init__(self, config: PPOConfig) -> None:
        self.config = config
        self.ppo_trainer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

    def setup(self, model: Any, ref_model: Optional[Any] = None, tokenizer: Any = None, dataset: Any = None):
        """
        Initialize the PPO Trainer from TRL.
        """
        try:
            from trl import PPOTrainer, PPOConfig as TRLPPOConfig, create_reference_model
            from transformers import AutoTokenizer
            
            # 1. Setup TRL PPO Config
            trl_config = TRLPPOConfig(
                learning_rate=self.config.learning_rate,
                batch_size=self.config.batch_size,
                mini_batch_size=self.config.mini_batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                optimize_cuda_cache=self.config.optimize_cuda_cache,
                early_stopping=self.config.early_stopping,
                target_kl=self.config.target_kl,
                ppo_epochs=self.config.ppo_epochs,
                seed=self.config.seed,
            )

            # 2. Prepare models
            if ref_model is None:
                ref_model = create_reference_model(model)

            # 3. Initialize PPOTrainer
            self.ppo_trainer = PPOTrainer(
                config=trl_config,
                model=model,
                ref_model=ref_model,
                tokenizer=tokenizer,
                dataset=dataset,
            )
            
            logger.info("PPOTrainer setup complete")
        except ImportError:
            logger.error("trl or transformers not installed. Please install them to use PPO.")
            raise

    def train(self, reward_model_pipeline: Any):
        """
        Execute the PPO training loop.
        """
        if self.ppo_trainer is None:
            raise RuntimeError("Call setup() before train()")

        generation_kwargs = {
            "min_length": -1,
            "top_k": 0.0,
            "top_p": 1.0,
            "do_sample": True,
            "pad_token_id": self.ppo_trainer.tokenizer.pad_token_id,
            "max_new_tokens": 32,
        }

        logger.info("Starting PPO training loop...")
        
        for epoch in range(self.config.ppo_epochs):
            for batch in self.ppo_trainer.dataloader:
                query_tensors = batch["input_ids"]

                # Get response from policy model
                response_tensors = self.ppo_trainer.generate(query_tensors, **generation_kwargs)
                batch["response"] = [self.ppo_trainer.tokenizer.decode(r.squeeze()) for r in response_tensors]

                # Compute rewards
                texts = [q + r for q, r in zip(batch["query"], batch["response"])]
                # Assuming reward_model_pipeline has a batch_score method
                rewards = reward_model_pipeline.batch_score(batch["query"], batch["response"])
                reward_tensors = [torch.tensor(reward) for reward in rewards]

                # Run PPO step
                stats = self.ppo_trainer.step(query_tensors, response_tensors, reward_tensors)
                self.ppo_trainer.log_stats(stats, batch, reward_tensors)

        logger.info("PPO training complete")
        self.save()

    def save(self, path: Optional[str] = None):
        """Save the PPO-aligned model."""
        out_path = path or self.config.output_dir
        if self.ppo_trainer:
            self.ppo_trainer.save_pretrained(out_path)
            logger.info(f"PPO model saved to {out_path}")
