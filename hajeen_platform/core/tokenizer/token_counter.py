from __future__ import annotations

import re
from typing import Any


class TokenCounter:
    """Count tokens using a tokenizer or a fast heuristic fallback."""

    _WORD_RE = re.compile(r"\S+")

    def count(self, text: str, tokenizer: Any) -> int:
        """Return the number of tokens for *text* using *tokenizer*."""
        if not text:
            return 0
        try:
            ids = tokenizer.encode(text)
            return len(ids)
        except Exception:
            return self._heuristic_count(text)

    @staticmethod
    def estimate(text: str, chars_per_token: float = 4.0) -> int:
        """Fast character-based estimate (no tokenizer needed)."""
        if not text:
            return 0
        return max(1, int(len(text) / chars_per_token))

    def _heuristic_count(self, text: str) -> int:
        words = self._WORD_RE.findall(text)
        return max(1, int(len(words) * 1.33))

    def fits_in_context(self, text: str, max_tokens: int, tokenizer: Any) -> bool:
        return self.count(text, tokenizer) <= max_tokens

    def remaining_tokens(self, used: int, context_limit: int) -> int:
        return max(0, context_limit - used)
