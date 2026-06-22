import json
import os
from typing import List, Dict, Any
from hajeen_platform.core.inference_engine.engine import get_inference_engine

class EvaluationFramework:
    def __init__(self):
        self.engine = get_inference_engine()
        # Try multiple possible paths for the benchmark dataset
        possible_paths = [
            "hajeen_model/datasets/evaluation_benchmark.jsonl",
            "hajeen_platform/hajeen_model/datasets/evaluation_benchmark.jsonl",
            "/home/ubuntu/hajeen_project/hajeen_platform/hajeen_model/datasets/evaluation_benchmark.jsonl"
        ]
        self.benchmark_dataset_path = next((p for p in possible_paths if os.path.exists(p)), possible_paths[0])

        self.benchmark_dataset = self._load_benchmark_dataset()

    def _load_benchmark_dataset(self) -> List[Dict]:
        try:
            with open(self.benchmark_dataset_path, "r", encoding="utf-8") as f:
                return [json.loads(line) for line in f]
        except FileNotFoundError:
            print(f"Warning: Benchmark dataset not found at {self.benchmark_dataset_path}. Using default.")
            return [
                {"instruction": "ما هو عاصمة السعودية؟", "expected": "الرياض", "language": "ar"},
                {"instruction": "What is the capital of France?", "expected": "Paris", "language": "en"},
                {"instruction": "كيف حالك؟", "expected": "أنا بخير، كيف يمكنني مساعدتك؟", "language": "ar"},
                {"instruction": "Translate 'Hello' to Arabic.", "expected": "مرحباً", "language": "en"},
                {"instruction": "من هو مؤسس المملكة العربية السعودية؟", "expected": "الملك عبد العزيز آل سعود", "language": "ar"},
                {"instruction": "Who is the current CEO of Google?", "expected": "Sundar Pichai", "language": "en"},
            ]

    async def run_automatic_evaluation(self, test_samples: List[Dict] = None) -> Dict:
        samples = test_samples or self.benchmark_dataset
        results = []
        correct_accuracy = 0
        
        # Ensure the engine is initialized
        await self.engine.initialize()

        for sample in samples:
            instruction = sample["instruction"]
            expected_response = sample["expected"]
            
            # Use the platform's core inference engine
            try:
                response_obj = await self.engine.infer(messages=[{"role": "user", "content": instruction}])
                actual_response = response_obj.content
            except Exception as e:
                actual_response = f"Error during inference: {str(e)}"

            # Simple accuracy check (exact match or inclusion for now)
            is_correct_accuracy = expected_response.lower() in actual_response.lower()
            if is_correct_accuracy:
                correct_accuracy += 1
            
            # Placeholder for more advanced metrics (Consistency, Response Quality)
            # These would typically require more sophisticated NLP techniques or human evaluation
            consistency_score = 0.0 # To be implemented
            response_quality_score = 0.0 # To be implemented

            results.append({
                "instruction": instruction,
                "expected": expected_response,
                "response": actual_response,
                "is_correct_accuracy": is_correct_accuracy,
                "consistency_score": consistency_score,
                "response_quality_score": response_quality_score,
                "language": sample.get("language", "unknown")
            })
        
        total_samples = len(samples)
        accuracy = correct_accuracy / total_samples if total_samples else 0
        
        # Aggregate other metrics if implemented
        avg_consistency = sum([r["consistency_score"] for r in results]) / total_samples if total_samples else 0
        avg_quality = sum([r["response_quality_score"] for r in results]) / total_samples if total_samples else 0

        return {
            "accuracy": accuracy,
            "total_samples": total_samples,
            "avg_consistency_score": avg_consistency,
            "avg_response_quality_score": avg_quality,
            "results": results
        }

    def save_evaluation_report(self, report: Dict, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=4)

    async def evaluate_and_save_report(self, output_filepath: str = "evaluation_report.json"):
        print("Running automatic evaluation...")
        report = await self.run_automatic_evaluation()
        self.save_evaluation_report(report, output_filepath)
        print(f"Evaluation report saved to {output_filepath}")
        return report
