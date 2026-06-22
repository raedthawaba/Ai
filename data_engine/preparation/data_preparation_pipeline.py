
from typing import List, Dict
from .data_validator import DataValidator
from .deduplicator import Deduplicator
from .quality_scorer import QualityScorer
from .language_detector import LanguageDetector
from .dataset_statistics import DatasetStatistics

class DataPreparationPipeline:
    def __init__(self, deduplication_threshold: float = 0.8):
        self.validator = DataValidator()
        self.deduplicator = Deduplicator(threshold=deduplication_threshold)
        self.scorer = QualityScorer()
        self.lang_detector = LanguageDetector()
        self.stats_generator = DatasetStatistics()

    def run(self, dataset: List[Dict], min_quality_score: int = 0) -> List[Dict]:
        print("Starting data preparation pipeline...")

        # 1. Validation
        print("Running data validation...")
        validated_dataset = self.validator.validate_dataset(dataset)
        print(f"Validated {len(validated_dataset)} samples.")

        # 2. Language Detection and Filtering
        print("Detecting and filtering languages...")
        lang_filtered_dataset = self.lang_detector.filter_unsupported_languages(validated_dataset)
        print(f"Filtered to {len(lang_filtered_dataset)} samples after language detection.")

        # 3. Quality Scoring
        print("Scoring data quality...")
        scored_dataset = self.scorer.score_dataset(lang_filtered_dataset)
        print(f"Scored {len(scored_dataset)} samples.")

        # Filter by minimum quality score
        quality_filtered_dataset = [sample for sample in scored_dataset if sample.get("quality_score", 0) >= min_quality_score]
        print(f"Filtered to {len(quality_filtered_dataset)} samples with quality score >= {min_quality_score}.")

        # 4. Deduplication
        print("Running deduplication...")
        deduplicated_dataset = self.deduplicator.deduplicate_dataset(quality_filtered_dataset)
        print(f"Deduplicated to {len(deduplicated_dataset)} unique samples.")

        print("Data preparation pipeline finished.")
        return deduplicated_dataset

    def generate_and_save_statistics(self, dataset: List[Dict], filepath: str):
        print("Generating dataset statistics...")
        stats = self.stats_generator.generate_statistics(dataset)
        self.stats_generator.save_statistics(stats, filepath)
        print(f"Statistics saved to {filepath}")
        return stats
