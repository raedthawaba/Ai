from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


class GenericTokenizer:
    """AutoTokenizer-backed generic tokenizer with a regex fallback."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._tokenizer = None
        self._load()

    def _load(self) -> None:
        try:
            from transformers import AutoTokenizer  # type: ignore

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, use_fast=True
            )
            logger.info("GenericTokenizer loaded via AutoTokenizer: %s", self.model_name)
        except Exception as exc:
            logger.warning(
                "Cannot load AutoTokenizer for '%s' (%s). Using regex fallback.",
                self.model_name,
                exc,
            )

    def encode(self, text: str) -> List[int]:
        if self._tokenizer is not None:
            return self._tokenizer.encode(text, add_special_tokens=False)
        tokens = re.findall(r"\w+|[^\w\s]|\s+", text)
        return [abs(hash(t)) % 100_000 for t in tokens]

    def decode(self, token_ids: List[int]) -> str:
        if self._tokenizer is not None:
            return self._tokenizer.decode(token_ids, skip_special_tokens=True)
        return f"<decoded {len(token_ids)} tokens>"

    def tokenize(self, text: str) -> List[str]:
        if self._tokenizer is not None:
            return self._tokenizer.tokenize(text)
        return re.findall(r"\w+|[^\w\s]", text)

    @property
    def vocab_size(self) -> int:
        if self._tokenizer is not None:
            return len(self._tokenizer)
        return 50_257

    def __repr__(self) -> str:
        return f"GenericTokenizer(model='{self.model_name}')"
