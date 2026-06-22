
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_engine.preparation.data_preparation_pipeline import DataPreparationPipeline

def test_pipeline():
    # Sample dataset
    dataset = [
        {"instruction": "ما هو نموذج هجين؟", "output": "نموذج هجين هو نموذج لغوي متطور."},
        {"instruction": "ما هو نموذج هجين؟", "output": "نموذج هجين هو نموذج لغوي متطور."}, # Exact duplicate
        {"instruction": "ما هو نموذج هجين؟", "output": "نموذج هجين هو نموذج لغوي متطور جداً."}, # Near duplicate
        {"instruction": "Short", "output": "Short"}, # Too short, should be penalized
        {"instruction": "Hello, what is Hajeen?", "output": "Hajeen is an advanced AI platform."}, # English
        {"instruction": "C'est quoi Hajeen?", "output": "Hajeen est une plateforme d'IA."}, # French (unsupported)
        {"instruction": "", "output": "Empty instruction"}, # Invalid
    ]

    pipeline = DataPreparationPipeline(deduplication_threshold=0.8)
    
    # Run the pipeline
    processed_dataset = pipeline.run(dataset, min_quality_score=50)
    
    print("\nProcessed Dataset Results:")
    for i, sample in enumerate(processed_dataset):
        print(f"Sample {i+1}: {sample.get('instruction')} (Score: {sample.get('quality_score')}, Lang: {sample.get('instruction_lang')})")

    # Generate and save statistics
    stats_filepath = "/home/ubuntu/hajeen_platform/logs/test_dataset_stats.json"
    stats = pipeline.generate_and_save_statistics(processed_dataset, stats_filepath)
    
    print("\nDataset Statistics:")
    print(f"Total Samples: {stats['num_samples']}")
    print(f"Language Distribution: {stats['language_distribution']}")
    print(f"Quality Score Distribution: {stats['quality_score_distribution']}")

if __name__ == "__main__":
    test_pipeline()
