import json
import re
import os

input_file = "datasets/raw/arabic_wiki.jsonl"
output_file = "datasets/cleaned_arabic_dataset.jsonl"

os.makedirs("datasets", exist_ok=True)

seen = set()
saved = 0
removed = 0

def clean_text(text):
    text = re.sub(r"http\\S+", "", text)
    text = re.sub(r"www\\S+", "", text)
    text = re.sub(r"\\s+", " ", text)
    text = text.strip()
    return text

with open(input_file, "r", encoding="utf-8") as infile, \
     open(output_file, "w", encoding="utf-8") as outfile:

    for line in infile:
        try:
            item = json.loads(line)

            text = clean_text(item["text"])

            if len(text) < 200:
                removed += 1
                continue

            if text in seen:
                removed += 1
                continue

            seen.add(text)

            record = {
                "text": text,
                "language": "ar",
                "source": item.get("source", "unknown")
            }

            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved += 1

        except:
            removed += 1

print("================================")
print("Cleaning completed")
print("Saved:", saved)
print("Removed:", removed)
print("Output:", output_file)
print("================================")
