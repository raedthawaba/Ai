# Hajeen Fine-Tuning Guide

## Overview

Fine-tuning adapts a pretrained Hajeen model to a specific task without training from scratch.
The same TrainingPipeline is used — you simply load an existing checkpoint and continue training
on a domain-specific dataset with a lower learning rate.

---

## Full Fine-Tuning

Load a pretrained model and fine-tune all parameters:

```python
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer
from hajeen_model.datasets.dataset_builder import DatasetBuilder
from hajeen_model.training.training_pipeline import TrainingPipeline, TrainingConfig

# Load pretrained
model = HajeenForCausalLM.from_pretrained("checkpoints/hajeen_1b/")
tokenizer = HajeenTokenizer.from_pretrained("tokenizer_model/")

# Domain-specific dataset (e.g., Arabic legal text)
builder = DatasetBuilder(tokenizer, max_seq_len=2048)
train_ds, val_ds = builder.build(["data/legal_arabic.txt"])

# Fine-tune with lower LR
config = TrainingConfig(
    output_dir="outputs/hajeen_1b_legal/",
    learning_rate=1e-5,         # 10-30x lower than pretraining LR
    warmup_steps=100,
    max_steps=5_000,
    batch_size=4,
    gradient_accumulation_steps=4,
    save_every_n_steps=500,
)
pipeline = TrainingPipeline(model, tokenizer, train_ds, val_ds, config)
pipeline.train()
```

---

## Parameter-Efficient Fine-Tuning (LoRA style)

For large models where full fine-tuning is too expensive, freeze the base model
and add trainable adapter layers:

```python
import torch.nn as nn

def freeze_base_model(model):
    """Freeze all parameters except layer norms and the LM head."""
    for name, param in model.named_parameters():
        if "norm" in name or "lm_head" in name:
            param.requires_grad = True
        else:
            param.requires_grad = False

freeze_base_model(model)

# Check what's trainable
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = model.num_parameters()
print(f"Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M ({trainable/total*100:.1f}%)")
```

---

## Instruction Fine-Tuning Format

Format your data as instruction-response pairs:

```
<bos>### Instruction:
اشرح مفهوم الشبكات العصبية باختصار.

### Response:
الشبكات العصبية هي نماذج حسابية مستوحاة من الدماغ البشري...<eos>
```

```python
def format_instruction(instruction: str, response: str) -> str:
    return f"### Instruction:\n{instruction}\n\n### Response:\n{response}"

# Build dataset from instruction pairs
instructions = [
    {"instruction": "...", "response": "..."},
    # ...
]
texts = [format_instruction(d["instruction"], d["response"]) for d in instructions]

# Train normally
builder = DatasetBuilder(tokenizer, max_seq_len=1024)
train_ds, val_ds = builder.build_from_texts(texts)  # or write to file first
```

---

## Resuming Fine-Tuning

```python
pipeline = TrainingPipeline(model, tokenizer, train_ds, val_ds, config)
pipeline.resume_from_checkpoint("outputs/hajeen_1b_legal/")
pipeline.train()
```

---

## Evaluation After Fine-Tuning

```python
from hajeen_model.evaluation.evaluation_pipeline import EvaluationPipeline

eval_pipeline = EvaluationPipeline(model, tokenizer)
result = eval_pipeline.evaluate(val_ds)
print(result.summary())

# Perplexity on domain text
ppl = eval_pipeline.perplexity_on_texts([
    "النص القانوني المتعلق بقانون العمل...",
])
print(f"Domain perplexity: {ppl:.2f}")
```
