from transformers import GPT2Config
from transformers import GPT2LMHeadModel
import os

config = GPT2Config(
    vocab_size=32000,
    n_positions=512,
    n_ctx=512,
    n_embd=512,
    n_layer=8,
    n_head=8,
    bos_token_id=1,
    eos_token_id=2
)

model = GPT2LMHeadModel(config)

os.makedirs("hajeen_large_model", exist_ok=True)

model.save_pretrained(
    "hajeen_large_model"
)

print("========================================")
print("LARGE MODEL CREATED")
print("========================================")
print("Parameters:", model.num_parameters())
