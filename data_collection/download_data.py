from datasets import load_dataset
import json
import os

os.makedirs("datasets/raw", exist_ok=True)

print("Downloading Arabic Wikipedia dataset...")

dataset = load_dataset(
    "wikimedia/wikipedia",
    "20231101.ar",
    split="train[:1%]"
)

output_file = "datasets/raw/arabic_wiki.jsonl"

count = 0

with open(output_file, "w", encoding="utf-8") as f:
    for item in dataset:
        text = item.get("text", "").strip()

        if len(text) > 200:
            record = {
                "text": text,
                "source": "arabic_wikipedia",
                "language": "ar"
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

print("===================================")
print("DONE")
print("Saved file:", output_file)
print("Saved samples:", count)
print("===================================")
