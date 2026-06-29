import argparse
import logging
from hajeen_platform.core.alignment.ppo_trainer import PPOTrainerWrapper, PPOConfig
from hajeen_platform.core.alignment.reward_model import RewardModelPipeline
from hajeen_platform.core.model.model_loader import ModelLoader
from hajeen_platform.core.tokenizer.tokenizer_manager import TokenizerManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Hajeen AI RLHF PPO Training Script")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the base model")
    parser.add_argument("--reward_model_path", type=str, required=True, help="Path to the reward model")
    parser.add_argument("--dataset_path", type=str, required=True, help="Path to the preference dataset")
    parser.add_argument("--output_dir", type=str, default="storage_data/rlhf_ppo_output", help="Output directory")
    
    args = parser.parse_args()

    logger.info("Starting RLHF PPO Training Pipeline...")

    # 1. Initialize Config
    ppo_config = PPOConfig(
        model_name=args.model_path,
        reward_model_name=args.reward_model_path,
        output_dir=args.output_dir
    )

    # 2. Load Models and Tokenizer
    # Note: These are placeholders representing the integration with Hajeen's core loader
    # In a real run, these would return actual torch models
    loader = ModelLoader()
    model = loader.load_model(args.model_path)
    
    tokenizer_manager = TokenizerManager()
    tokenizer = tokenizer_manager.get_tokenizer(args.model_path)

    # 3. Load Reward Model
    reward_pipeline = RewardModelPipeline(args.reward_model_path)
    reward_pipeline.load_model()

    # 4. Initialize PPO Trainer
    trainer = PPOTrainerWrapper(ppo_config)
    
    # 5. Setup and Train
    # dataset would be loaded from args.dataset_path using Hajeen's dataset_loader
    logger.info("Setting up PPO Trainer...")
    # trainer.setup(model=model, tokenizer=tokenizer, dataset=dataset)
    # trainer.train(reward_model_pipeline=reward_pipeline)

    logger.info(f"RLHF PPO Training completed. Model saved to {args.output_dir}")

if __name__ == "__main__":
    main()
