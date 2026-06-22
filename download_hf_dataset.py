from datasets import load_dataset
import os

print("Loading dataset from HuggingFace...")

dataset = load_dataset(
    "Raedthawaba/hajeen-datasets"
)

os.makedirs("datasets", exist_ok=True)

output_file = "datasets/full_dataset.jsonl"

with open(output_file, "w", encoding="utf-8") as f:
    for item in dataset["train"]:
        text = item["text"].replace("\n", " ").strip()
        f.write('{"text": "' + text.replace('"', '\\"') + '"}\n')

print("========================================")
print("DATASET DOWNLOADED")
print("Saved:", output_file)
print("Samples:", len(dataset["train"]))
print("========================================")
