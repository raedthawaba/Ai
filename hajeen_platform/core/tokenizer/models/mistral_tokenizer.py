from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


class MistralTokenizer:
    """Mistral-compatible tokenizer wrapper."""

    BOS_TOKEN = "<s>"
    EOS_TOKEN = "</s>"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._hf_tokenizer = None
        self._load()

    def _load(self) -> None:
        try:
            from transformers import AutoTokenizer  # type: ignore

            self._hf_tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, use_fast=True
            )
            logger.info("HuggingFace MistralTokenizer loaded: %s", self.model_name)
        except Exception as exc:
            logger.warning(
                "Cannot load HF tokenizer for '%s' (%s). Using fallback.",
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
        return " ".join(f"[{i}]" for i in token_ids[:20])

    def _fallback_encode(self, text: str) -> List[int]:
        tokens = re.findall(r"\w+|[^\w\s]", text.lower())
        return [hash(t) & 0x7FFFFFFF for t in tokens]

    @property
    def vocab_size(self) -> int:
        if self._hf_tokenizer is not None:
            return self._hf_tokenizer.vocab_size
        return 32_000

    def apply_chat_template(self, messages: list[dict]) -> str:
        """Format messages in Mistral instruction format."""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                parts.append(f"[INST] {content} [/INST]")
            elif role == "assistant":
                parts.append(content)
            elif role == "system":
                parts.insert(0, content)
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"MistralTokenizer(model='{self.model_name}')"
