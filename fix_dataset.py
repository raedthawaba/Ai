import json

input_file = "/teamspace/studios/this_studio/Ai/hajeen_platform/datasets/final_merged_dataset.jsonl"
output_file = "/teamspace/studios/this_studio/Ai/hajeen_platform/datasets/final_cleaned_dataset.jsonl"

good = 0
bad = 0

with open(input_file, "r", encoding="utf-8") as infile:
    with open(output_file, "w", encoding="utf-8") as outfile:

        for line in infile:
            try:
                data = json.loads(line)

                text = data.get("text", "")

                if not text.strip():
                    continue

                clean_data = {
                    "text": text.replace("\x00", " ")
                }

                outfile.write(
                    json.dumps(clean_data, ensure_ascii=False) + "\n"
                )

                good += 1

            except Exception:
                bad += 1

print("========================================")
print("GOOD SAMPLES:", good)
print("BAD SAMPLES:", bad)
print("CLEAN DATASET SAVED")
print("========================================")
