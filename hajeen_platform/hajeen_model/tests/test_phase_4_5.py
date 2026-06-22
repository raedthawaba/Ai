import sys
import os
import json
import unittest

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from hajeen_model.inference.inference_engine import InferenceEngine
from hajeen_model.inference.hajeen_provider import HajeenProvider
from hajeen_model.inference.ollama_provider import OllamaProvider
from hajeen_model.datasets.dataset_loader import DatasetLoader
from hajeen_model.training.checkpoint_manager import CheckpointManager

class TestPhase4And5(unittest.TestCase):
    
    def test_inference_engine_switching(self):
        print("\n--- Testing Inference Engine Switching ---")
        engine = InferenceEngine(provider_type="ollama")
        status = engine.get_status()
        print(f"Initial Provider: {status['engine_active_provider']}")
        self.assertEqual(status['engine_active_provider'], "ollama")
        
        engine.switch_provider("hajeen")
        status = engine.get_status()
        print(f"Switched Provider: {status['engine_active_provider']}")
        self.assertEqual(status['engine_active_provider'], "hajeen")

    def test_hajeen_provider_mock_response(self):
        print("\n--- Testing Hajeen Provider Response ---")
        provider = HajeenProvider()
        response = provider.generate("ما هو مستقبل الذكاء الاصطناعي؟")
        print(f"Response: {response}")
        self.assertIn("استجابة نموذج هجين", response)

    def test_dataset_loader(self):
        print("\n--- Testing Dataset Loader ---")
        # Create a dummy jsonl file
        test_file = "test_data.jsonl"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"instruction": "test inst", "input": "test input", "output": "test output"}) + "\n")
            f.write(json.dumps({"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]}) + "\n")
        
        loader = DatasetLoader(test_file)
        data = loader.load_jsonl()
        self.assertEqual(len(data), 2)
        
        formatted_alpaca = loader.format_for_training(data, format_type="alpaca")
        self.assertEqual(len(formatted_alpaca), 1) # Only the first one is alpaca
        
        formatted_chat = loader.format_for_training(data, format_type="chat")
        self.assertEqual(len(formatted_chat), 2) # Both can be chat (alpaca converted)
        
        stats = loader.get_statistics(data)
        print(f"Dataset Stats: {stats}")
        self.assertEqual(stats['total_samples'], 2)
        
        os.remove(test_file)

    def test_checkpoint_manager(self):
        print("\n--- Testing Checkpoint Manager ---")
        cp_dir = "test_checkpoints"
        manager = CheckpointManager(checkpoint_dir=cp_dir)
        
        metrics = {"loss": 0.5, "accuracy": 0.8}
        path = manager.save_checkpoint(None, epoch=1, metrics=metrics)
        print(f"Checkpoint saved at: {path}")
        
        checkpoints = manager.list_checkpoints()
        self.assertTrue(len(checkpoints) > 0)
        
        meta = manager.load_latest_metadata()
        self.assertEqual(meta['metrics']['loss'], 0.5)
        
        import shutil
        shutil.rmtree(cp_dir)

if __name__ == "__main__":
    unittest.main()
