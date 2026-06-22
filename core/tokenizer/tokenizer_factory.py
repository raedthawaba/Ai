from __future__ import annotations

import logging
from typing import Any

from .models.llama_tokenizer import LlamaTokenizer
from .models.mistral_tokenizer import MistralTokenizer
from .models.generic_tokenizer import GenericTokenizer

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type] = {
    "llama": LlamaTokenizer,
    "mistral": MistralTokenizer,
    "generic": GenericTokenizer,
}


class TokenizerFactory:
    """Instantiate the right tokenizer implementation by model type."""

    def create(self, model_name: str, model_type: str = "generic") -> Any:
        key = model_type.lower()
        cls = _REGISTRY.get(key)
        if cls is None:
            logger.warning(
                "Unknown model_type '%s', falling back to GenericTokenizer", model_type
            )
            cls = GenericTokenizer
        logger.debug("Creating %s tokenizer for model '%s'", cls.__name__, model_name)
        return cls(model_name)

    @staticmethod
    def supported_types() -> list[str]:
        return list(_REGISTRY.keys())
