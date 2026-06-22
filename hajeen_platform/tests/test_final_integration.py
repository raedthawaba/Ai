import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hajeen_platform.core.inference_engine.engine import get_inference_engine
from hajeen_platform.hajeen_model.evaluation.evaluation_framework import EvaluationFramework

async def test_inference():
    print("\n--- Testing Inference Engine ---")
    engine = get_inference_engine()
    await engine.initialize()
    
    messages = [{"role": "user", "content": "مرحباً، من أنت؟"}]
    response = await engine.infer(messages=messages)
    
    print(f"Provider: {response.provider}")
    print(f"Model: {response.model}")
    print(f"Response: {response.cleaned_content}")
    
    assert "hajeen" in response.provider.lower()
    print("Inference Engine Test Passed!")

async def test_evaluation():
    print("\n--- Testing Evaluation Framework ---")
    eval_framework = EvaluationFramework()
    os.makedirs("tests", exist_ok=True)
    report = await eval_framework.evaluate_and_save_report("tests/test_evaluation_report.json")
    
    print(f"Accuracy: {report['accuracy'] * 100}%")
    print(f"Total Samples: {report['total_samples']}")
    
    assert report['total_samples'] > 0
    assert os.path.exists("tests/test_evaluation_report.json")
    print("Evaluation Framework Test Passed!")

async def main():
    try:
        await test_inference()
        await test_evaluation()
        print("\nAll integration tests passed successfully!")
    except Exception as e:
        print(f"\nTests failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
