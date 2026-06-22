from datasets import load_dataset
from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import Whitespace

print("Loading final dataset...")

dataset = load_dataset(
    "json",
    data_files="/teamspace/studios/this_studio/Ai/hajeen_platform/datasets/final_cleaned_dataset.jsonl"
)

print("Dataset loaded")
print("Samples:", len(dataset["train"]))

tokenizer = Tokenizer(BPE(unk_token="[UNK]"))
tokenizer.pre_tokenizer = Whitespace()

trainer = BpeTrainer(
    vocab_size=32000,
    special_tokens=[
        "[UNK]",
        "[PAD]",
        "[CLS]",
        "[SEP]",
        "[MASK]"
    ]
)

def batch_iterator():
    for item in dataset["train"]:
        yield item["text"]

print("Training tokenizer on large dataset...")

tokenizer.train_from_iterator(
    batch_iterator(),
    trainer=trainer
)

tokenizer.save("tokenizer_output/tokenizer.json")

print("========================================")
print("LARGE TOKENIZER TRAINED")
print("========================================")
