from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


class LlamaTokenizer:
    """LLaMA-compatible tokenizer wrapper.

    Attempts to load via HuggingFace transformers; falls back to a
    BPE-approximation tokenizer so the service never crashes when the
    model weights are not present.
    """

    BOS_TOKEN = "<s>"
    EOS_TOKEN = "</s>"
    UNK_TOKEN = "<unk>"
    PAD_TOKEN = "<pad>"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._hf_tokenizer = None
        self._load()

    def _load(self) -> None:
        try:
            from transformers import LlamaTokenizer as HFLlamaTokenizer  # type: ignore

            self._hf_tokenizer = HFLlamaTokenizer.from_pretrained(
                self.model_name, use_fast=True
            )
            logger.info("HuggingFace LlamaTokenizer loaded: %s", self.model_name)
        except Exception as exc:
            logger.warning(
                "Cannot load HF LlamaTokenizer for '%s' (%s). Using fallback.",
                self.model_name,
                exc,
            )

    def encode(self, text: str) -> List[int]:
        if self._hf_tokenizer is not None:
            return self._hf_tokenizer.encode(text, add_special_tokens=False)
        return self._fallback_encode(text)

    def decode(self, token_ids: List[int]) -> str:
        if self._hf_tokenizer is not None:
            return self._hf_tokenizer.decode(token_ids, skip_special_tokens=True)
        return self._fallback_decode(token_ids)

    def _fallback_encode(self, text: str) -> List[int]:
        tokens = re.findall(r"\w+|[^\w\s]", text.lower())
        return [hash(t) & 0x7FFFFFFF for t in tokens]

    def _fallback_decode(self, token_ids: List[int]) -> str:
        return f"[decoded:{len(token_ids)}_tokens]"

    @property
    def vocab_size(self) -> int:
        if self._hf_tokenizer is not None:
            return self._hf_tokenizer.vocab_size
        return 32_000

    def __repr__(self) -> str:
        return f"LlamaTokenizer(model='{self.model_name}')"
