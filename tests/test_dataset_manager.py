
import sys
import os
import json
import shutil

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hajeen_model.datasets.dataset_manager import DatasetManager

def test_dataset_manager():
    print("--- Testing Dataset Manager (Phase 3) ---")
    
    storage_dir = "/home/ubuntu/hajeen_platform/hajeen_model/datasets/test_manager"
    if os.path.exists(storage_dir):
        shutil.rmtree(storage_dir)
    
    manager = DatasetManager(storage_dir=storage_dir)
    
    # 1. Load Data
    print("\n[1/6] Testing Load Data...")
    test_jsonl = os.path.join(storage_dir, "test.jsonl")
    os.makedirs(storage_dir, exist_ok=True)
    with open(test_jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"instruction": "test 1", "output": "output 1"}) + "\n")
        f.write(json.dumps({"instruction": "test 2", "output": "output 2"}) + "\n")
    
    data = manager.load_data(test_jsonl)
    print(f"Loaded {len(data)} samples.")
    assert len(data) == 2

    # 2. Merge Data
    print("\n[2/6] Testing Merge Data...")
    merged = manager.merge_datasets([data, data])
    print(f"Merged count: {len(merged)}")
    assert len(merged) == 4

    # 3. Split Data
    print("\n[3/6] Testing Split Data...")
    train, test = manager.split_dataset(merged, train_ratio=0.75)
    print(f"Split: Train={len(train)}, Test={len(test)}")
    assert len(train) == 3 and len(test) == 1

    # 4. Quality Check
    print("\n[4/6] Testing Quality Check...")
    quality_data = manager.perform_quality_check(merged, min_quality_score=0)
    print(f"Quality check returned {len(quality_data)} samples.")

    # 5. Versioning
    print("\n[5/6] Testing Versioning...")
    version_path = manager.process_and_version(merged, "dataset_v1")
    print(f"Versioned at: {version_path}")
    assert os.path.exists(version_path)

    # 6. Statistics
    print("\n[6/6] Testing Statistics & Listing...")
    stats = manager.get_statistics("dataset_v1")
    print(f"Stats for v1: {stats.get('num_samples')} samples.")
    
    versions = manager.list_versions()
    print(f"Versions found: {versions}")
    assert "dataset_v1" in versions

    print("\n--- Dataset Manager Test Completed Successfully ---")

if __name__ == "__main__":
    test_dataset_manager()
