from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any
from threading import Lock

from .tokenizer_factory import TokenizerFactory
from .token_counter import TokenCounter

logger = logging.getLogger(__name__)


class TokenizerManager:
    """Singleton manager that owns all loaded tokenizers."""

    _instance: Optional["TokenizerManager"] = None
    _lock: Lock = Lock()

    def __new__(cls) -> "TokenizerManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._tokenizers: Dict[str, Any] = {}
        self._factory = TokenizerFactory()
        self._counter = TokenCounter()
        self._initialized = True
        logger.info("TokenizerManager initialized")

    def get_tokenizer(self, model_name: str, model_type: str = "generic") -> Any:
        """Return cached tokenizer or load a new one."""
        key = f"{model_type}:{model_name}"
        if key not in self._tokenizers:
            logger.info("Loading tokenizer: %s (type=%s)", model_name, model_type)
            tokenizer = self._factory.create(model_name, model_type)
            self._tokenizers[key] = tokenizer
        return self._tokenizers[key]

    def count_tokens(self, text: str, model_name: str, model_type: str = "generic") -> int:
        tokenizer = self.get_tokenizer(model_name, model_type)
        return self._counter.count(text, tokenizer)

    def encode(self, text: str, model_name: str, model_type: str = "generic") -> List[int]:
        tokenizer = self.get_tokenizer(model_name, model_type)
        return tokenizer.encode(text)

    def decode(self, token_ids: List[int], model_name: str, model_type: str = "generic") -> str:
        tokenizer = self.get_tokenizer(model_name, model_type)
        return tokenizer.decode(token_ids)

    def truncate_to_limit(
        self,
        text: str,
        max_tokens: int,
        model_name: str,
        model_type: str = "generic",
    ) -> str:
        """Truncate *text* so it fits within *max_tokens*."""
        tokenizer = self.get_tokenizer(model_name, model_type)
        ids = tokenizer.encode(text)
        if len(ids) <= max_tokens:
            return text
        ids = ids[:max_tokens]
        return tokenizer.decode(ids)

    def list_loaded(self) -> List[str]:
        return list(self._tokenizers.keys())

    def unload(self, model_name: str, model_type: str = "generic") -> bool:
        key = f"{model_type}:{model_name}"
        if key in self._tokenizers:
            del self._tokenizers[key]
            logger.info("Tokenizer unloaded: %s", key)
            return True
        return False

    def clear_all(self) -> None:
        self._tokenizers.clear()
        logger.info("All tokenizers cleared")
