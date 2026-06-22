from tokenizers import Tokenizer
from transformers import PreTrainedTokenizerFast
import os

tokenizer = Tokenizer.from_file(
    "tokenizer_output/tokenizer.json"
)

hf_tokenizer = PreTrainedTokenizerFast(
    tokenizer_object=tokenizer,
    unk_token="[UNK]",
    pad_token="[PAD]",
    cls_token="[CLS]",
    sep_token="[SEP]",
    mask_token="[MASK]"
)

os.makedirs("hajeen_large_tokenizer", exist_ok=True)

hf_tokenizer.save_pretrained(
    "hajeen_large_tokenizer"
)

print("========================================")
print("LARGE TOKENIZER EXPORTED")
print("========================================")
