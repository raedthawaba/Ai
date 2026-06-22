from datasets import load_dataset
from transformers import (
    GPT2LMHeadModel,
    PreTrainedTokenizerFast,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments
)

dataset = load_dataset(
    "json",
    data_files="datasets/final_cleaned_dataset.jsonl"
)

tokenizer = PreTrainedTokenizerFast.from_pretrained(
    "hajeen_large_tokenizer"
)

model = GPT2LMHeadModel.from_pretrained(
    "hajeen_large_model"
)

def tokenize(example):
    return tokenizer(
        example["text"],
        truncation=True,
        max_length=128
    )

tokenized = dataset.map(
    tokenize,
    batched=True,
    remove_columns=["text"]
)

data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False
)

training_args = TrainingArguments(
    output_dir="hajeen_large_trained",
    per_device_train_batch_size=2,
    num_train_epochs=1,
    save_steps=1000,
    logging_steps=50
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized["train"],
    data_collator=data_collator
)

trainer.train()

trainer.save_model(
    "hajeen_large_trained"
)

print("========================================")
print("LARGE TRAINING FINISHED")
print("========================================")
