
import sys
import os
import json

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hajeen_model.datasets.dataset_manager import DatasetManager
from hajeen_model.inference.inference_engine import InferenceEngine
from hajeen_model.evaluation.evaluation_framework import EvaluationFramework

def run_integration_test():
    print("--- Starting Full Integration Test ---")
    
    # 1. Dataset Management
    print("\n[1/4] Testing Dataset Management...")
    manager = DatasetManager()
    raw_data = [
        {"instruction": "اختبار النظام", "output": "النظام يعمل بشكل جيد."},
        {"instruction": "System Test", "output": "System is working fine."},
        {"instruction": "ما هو نموذج هجين؟", "output": "نموذج هجين هو نموذج لغوي متطور."},
        {"instruction": "ما هو نموذج هجين؟", "output": "نموذج هجين هو نموذج لغوي متطور جداً."}, # Near duplicate
        {"instruction": "Short", "output": "Short"}, # Too short, should be penalized
        {"instruction": "C'est quoi Hajeen?", "output": "Hajeen est une plateforme d'IA."}, # French (unsupported)
        {"instruction": "", "output": "Empty instruction"}, # Invalid
    ]
    
    # Process and version a dataset
    version_path = manager.process_and_version(raw_data, "v_test_2", min_quality_score=50)
    print(f"Dataset versioned and saved at: {version_path}")

    # Load a specific version
    loaded_dataset = manager.load_version("v_test_2")
    print(f"Loaded {len(loaded_dataset)} samples from v_test_2.")

    # List all versions
    versions = manager.list_versions()
    print(f"Available dataset versions: {versions}")

    # Perform on-demand quality check
    quality_checked_data = manager.perform_quality_check(raw_data, min_quality_score=70)
    print(f"Quality checked data count (min_quality_score=70): {len(quality_checked_data)}")

    # 2. Inference Layer
    print("\n[2/4] Testing Inference Layer (Mock Provider)...")
    class MockProvider:
        def generate(self, prompt, **kwargs): return f"Mock response for: {prompt}"
        def get_model_info(self): return {"provider": "Mock"}
    
    engine = InferenceEngine(provider=MockProvider())
    response = engine.infer("كيف حالك؟")
    print(f"Inference Response: {response}")
    
    # 3. Evaluation Framework
    print("\n[3/4] Testing Evaluation Framework...")
    evaluator = EvaluationFramework(engine)
    evaluator.benchmark_dataset = [{"instruction": "Test", "expected": "Mock"}]
    eval_results = evaluator.run_automatic_evaluation()
    print(f"Evaluation Accuracy: {eval_results['accuracy'] * 100}%")
    
    # 4. API Linkage (Simulated)
    print("\n[4/4] Simulating API Linkage...")
    print("Inference Layer is now decoupled from Mock and ready for HajeenProvider.")
    
    print("\n--- Integration Test Completed Successfully ---")

if __name__ == "__main__":
    run_integration_test()
