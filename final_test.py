from transformers import GPT2LMHeadModel
from transformers import PreTrainedTokenizerFast

tokenizer = PreTrainedTokenizerFast.from_pretrained(
    "hajeen_large_trained"
)

model = GPT2LMHeadModel.from_pretrained(
    "hajeen_large_trained"
)

prompt = "الذكاء الاصطناعي"

inputs = tokenizer(
    prompt,
    return_tensors="pt"
)

outputs = model.generate(
    **inputs,
    max_length=80,
    temperature=0.8,
    do_sample=True
)

result = tokenizer.decode(
    outputs[0],
    skip_special_tokens=True
)

print("========================================")
print("PROMPT:")
print(prompt)
print("========================================")
print("MODEL OUTPUT:")
print(result)
print("========================================")
