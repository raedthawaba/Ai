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
