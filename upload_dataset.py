from datasets import load_dataset
from huggingface_hub import login

# dataset path
dataset_path = "datasets/cleaned_arabic_dataset.jsonl"

# load dataset
dataset = load_dataset(
    "json",
    data_files=dataset_path
)

# push to huggingface
dataset.push_to_hub(
    "Raedthawaba/hajeen-datasets"
)

print("===================================")
print("Dataset uploaded successfully")
print("Repo: Raedthawaba/hajeen-datasets")
print("===================================")
