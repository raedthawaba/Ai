from __future__ import annotations

from typing import List, Optional


class StoppingCriteria:
    """Determine when to stop generation based on stop sequences or length."""

    def __init__(
        self,
        stop_sequences: Optional[List[str]] = None,
        max_tokens: int = 512,
        eos_token_id: Optional[int] = None,
    ) -> None:
        self.stop_sequences = stop_sequences or []
        self.max_tokens = max_tokens
        self.eos_token_id = eos_token_id
        self._token_count = 0

    def reset(self) -> None:
        self._token_count = 0

    def should_stop_on_token(self, token_id: int) -> bool:
        self._token_count += 1
        if self._token_count >= self.max_tokens:
            return True
        if self.eos_token_id is not None and token_id == self.eos_token_id:
            return True
        return False

    def should_stop_on_text(self, generated_text: str) -> bool:
        for seq in self.stop_sequences:
            if seq in generated_text:
                return True
        return False

    def truncate_at_stop(self, text: str) -> str:
        for seq in self.stop_sequences:
            idx = text.find(seq)
            if idx != -1:
                return text[:idx]
        return text

    @property
    def tokens_generated(self) -> int:
        return self._token_count


class HuggingFaceStoppingCriteria:
    """Adapter for HuggingFace transformers StoppingCriteria interface."""

    def __init__(self, stop_sequences: List[str], tokenizer: object) -> None:
        self.stop_sequences = stop_sequences
        self.tokenizer = tokenizer

    def __call__(self, input_ids: object, scores: object, **kwargs: object) -> bool:
        try:
            generated = self.tokenizer.decode(  # type: ignore
                input_ids[0][-50:], skip_special_tokens=True
            )
            return any(seq in generated for seq in self.stop_sequences)
        except Exception:
            return False
