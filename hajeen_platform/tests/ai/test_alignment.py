import pytest
import os
import json
from hajeen_platform.core.alignment.preference_dataset import PreferenceDatasetBuilder
from hajeen_platform.core.alignment.reward_model import RewardModelPipeline
from hajeen_platform.core.alignment.evaluation_system import AlignmentEvaluator
from hajeen_platform.core.alignment.alignment_pipeline import AlignmentPipeline

def test_preference_dataset_builder(tmp_path):
    output_dir = tmp_path / "alignment"
    builder = PreferenceDatasetBuilder(output_path=str(output_dir))
    
    builder.add_example("Hello", "Hi there!", "Go away")
    saved_path = builder.save("test_prefs.jsonl")
    
    assert os.path.exists(saved_path)
    with open(saved_path, 'r') as f:
        data = json.loads(f.readline())
        assert data["prompt"] == "Hello"
        assert data["chosen"] == "Hi there!"
        assert data["rejected"] == "Go away"

def test_reward_model_pipeline():
    # Test with dummy scoring
    pipeline = RewardModelPipeline()
    score = pipeline.score_response("Test prompt", "Test response")
    assert score.score == 0.5
    
    ranking = pipeline.rank_responses("Prompt", ["Bad", "Good"])
    assert len(ranking) == 2
    assert ranking[0]["score"] == 0.5

def test_alignment_evaluator():
    evaluator = AlignmentEvaluator()
    results = evaluator.run_full_eval("Hello", "I am a helpful assistant")
    
    assert "safety" in results
    assert "quality" in results
    assert "overall_alignment_score" in results
    assert results["quality"]["helpfulness_score"] == 0.85

def test_alignment_pipeline(tmp_path):
    output_dir = tmp_path / "alignment_pipe"
    pipeline = AlignmentPipeline()
    pipeline.dataset_builder.output_path = output_dir
    
    raw_data = [
        {"prompt": "Q1", "chosen": "A1", "rejected": "B1"},
        {"prompt": "Q2", "chosen": "A2", "rejected": "B2"}
    ]
    
    path = pipeline.build_preference_dataset(raw_data, "pipe_test.jsonl")
    assert os.path.exists(path)

@pytest.mark.asyncio
async def test_dpo_pipeline_init():
    model = MockModel()
    ref_model = MockModel()
    tokenizer = MockTokenizer()
    pipeline = DPOPipeline(model, ref_model, tokenizer)
    assert pipeline is not None

@pytest.mark.asyncio
async def test_dpo_prepare_preference_data():
    model = MockModel()
    ref_model = MockModel()
    tokenizer = MockTokenizer()
    pipeline = DPOPipeline(model, ref_model, tokenizer)
    
    preferences = [
        {"prompt": "P1", "chosen_response": "C1", "rejected_response": "R1"},
        {"prompt": "P2", "chosen_response": "C2", "rejected_response": "R2"},
    ]
    processed_data = pipeline.prepare_preference_data(preferences)
    assert len(processed_data) == 2
    assert processed_data[0] == ("P1", "C1", "R1")

@pytest.mark.asyncio
async def test_dpo_run_pipeline():
    model = MockModel()
    ref_model = MockModel()
    tokenizer = MockTokenizer()
    pipeline = DPOPipeline(model, ref_model, tokenizer)
    
    preferences = [
        {"prompt": "P1", "chosen_response": "C1", "rejected_response": "R1"},
    ]
    results = await pipeline.run_pipeline(preferences, epochs=1)
    assert results["status"] == "completed"
    assert results["average_loss"] > 0

@pytest.mark.asyncio
async def test_rlhf_infrastructure_init():
    policy_model = MockPolicyModel()
    reward_model = MockRewardModel()
    tokenizer = MockTokenizer()
    infra = RLHFInfrastructure(policy_model, reward_model, tokenizer)
    assert infra is not None

@pytest.mark.asyncio
async def test_rlhf_collect_human_feedback():
    policy_model = MockPolicyModel()
    reward_model = MockRewardModel()
    tokenizer = MockTokenizer()
    infra = RLHFInfrastructure(policy_model, reward_model, tokenizer)
    
    prompts = ["Prompt A", "Prompt B"]
    feedback = await infra.collect_human_feedback(prompts)
    assert len(feedback) == 2
    assert "chosen_response" in feedback[0]

@pytest.mark.asyncio
async def test_rlhf_train_reward_model():
    policy_model = MockPolicyModel()
    reward_model = MockRewardModel()
    tokenizer = MockTokenizer()
    infra = RLHFInfrastructure(policy_model, reward_model, tokenizer)
    
    feedback = [
        {"prompt": "P1", "chosen_response": "C1", "rejected_response": "R1"},
    ]
    results = await infra.train_reward_model(feedback)
    assert results["status"] == "reward_model_trained"

@pytest.mark.asyncio
async def test_rlhf_run_pipeline():
    policy_model = MockPolicyModel()
    reward_model = MockRewardModel()
    tokenizer = MockTokenizer()
    infra = RLHFInfrastructure(policy_model, reward_model, tokenizer)
    
    initial_prompts = ["Prompt X"]
    results = await infra.run_rlhf_pipeline(initial_prompts, reward_model_epochs=1, ppo_steps=1)
    assert results["status"] == "completed"
    assert results["average_ppo_loss"] > 0
