from datasets import load_dataset

dataset = load_dataset(
    "json",
    data_files="/teamspace/studios/this_studio/Ai/hajeen_platform/datasets/final_cleaned_dataset.jsonl"
)

dataset["train"].push_to_hub(
    "raedthawaba/hajeen-datasets"
)

print("========================================")
print("FINAL DATASET UPLOADED")
print("========================================")
