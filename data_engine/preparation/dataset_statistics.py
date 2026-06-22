
from typing import List, Dict
import json

class DatasetStatistics:
    def __init__(self):
        pass

    def generate_statistics(self, dataset: List[Dict]) -> Dict:
        stats = {
            "num_samples": len(dataset),
            "total_words": 0,
            "total_tokens": 0, # Placeholder, requires tokenizer
            "avg_length": 0,
            "language_distribution": {},
            "quality_score_distribution": {},
            "validation_error_counts": {}
        }

        total_length = 0
        for sample in dataset:
            instruction = sample.get("instruction", "")
            output = sample.get("output", "")
            
            total_words_sample = len(instruction.split()) + len(output.split())
            stats["total_words"] += total_words_sample
            total_length += len(instruction) + len(output)

            # Language distribution
            instruction_lang = sample.get("instruction_lang")
            output_lang = sample.get("output_lang")
            if instruction_lang: # Assuming instruction_lang and output_lang are the same after filtering
                stats["language_distribution"][instruction_lang] = stats["language_distribution"].get(instruction_lang, 0) + 1

            # Quality score distribution
            quality_score = sample.get("quality_score")
            if quality_score is not None:
                score_range = f"{int(quality_score / 10) * 10}-{(int(quality_score / 10) * 10) + 9}"
                stats["quality_score_distribution"][score_range] = stats["quality_score_distribution"].get(score_range, 0) + 1

            # Validation error counts
            for error in sample.get("validation_errors", []):
                stats["validation_error_counts"][error] = stats["validation_error_counts"].get(error, 0) + 1

        if stats["num_samples"] > 0:
            stats["avg_length"] = total_length / stats["num_samples"]

        return stats

    def save_statistics(self, stats: Dict, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)

    def load_statistics(self, filepath: str) -> Dict:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
