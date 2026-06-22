from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ContextManager:
    """Manage and trim context windows for inference requests."""

    def __init__(self, max_context_tokens: int = 4096, reserve_tokens: int = 512) -> None:
        self.max_context_tokens = max_context_tokens
        self.reserve_tokens = reserve_tokens

    @property
    def available_context(self) -> int:
        return self.max_context_tokens - self.reserve_tokens

    def fit_messages(
        self,
        messages: List[Dict],
        tokenizer: Any,
        system_message: Optional[str] = None,
    ) -> List[Dict]:
        """Trim messages so they fit within the context window."""
        result: List[Dict] = []

        if system_message:
            system_tokens = self._count_text(system_message, tokenizer)
        else:
            system_tokens = 0

        budget = self.available_context - system_tokens
        trimmed: List[Dict] = []
        used = 0

        for msg in reversed(messages):
            tokens = self._count_text(msg.get("content", ""), tokenizer)
            if used + tokens > budget:
                break
            trimmed.insert(0, msg)
            used += tokens

        if system_message:
            result.append({"role": "system", "content": system_message})
        result.extend(trimmed)
        return result

    def fit_text(self, text: str, tokenizer: Any, max_tokens: Optional[int] = None) -> str:
        limit = max_tokens or self.available_context
        tokens = self._encode(text, tokenizer)
        if len(tokens) <= limit:
            return text
        truncated = tokens[:limit]
        return self._decode(truncated, tokenizer)

    def estimate_tokens(self, messages: List[Dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += max(1, len(content) // 4)
        return total

    def _count_text(self, text: str, tokenizer: Any) -> int:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            return max(1, len(text) // 4)

    def _encode(self, text: str, tokenizer: Any) -> List[int]:
        try:
            return tokenizer.encode(text)
        except Exception:
            words = text.split()
            return list(range(len(words)))

    def _decode(self, token_ids: List[int], tokenizer: Any) -> str:
        try:
            return tokenizer.decode(token_ids, skip_special_tokens=True)
        except Exception:
            return text[:len(token_ids) * 4]  # type: ignore
