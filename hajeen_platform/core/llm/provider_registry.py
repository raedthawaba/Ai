"""Phase 8.1 — Provider Registry: سجل ديناميكي لمزودي النماذج."""
from __future__ import annotations

import importlib
import logging
from typing import Dict, List, Optional, Type

from .base import BaseLLMProvider, LLMConfig

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    سجل ديناميكي لمزودي LLM.

    يتيح تسجيل، تحميل، واسترجاع المزودين بشكل ديناميكي
    دون الحاجة لتغيير الكود الأساسي.
    """

    _providers: Dict[str, Type[BaseLLMProvider]] = {}
    _aliases: Dict[str, str] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type[BaseLLMProvider],
                 aliases: Optional[List[str]] = None) -> None:
        """تسجيل مزود جديد."""
        cls._providers[name.lower()] = provider_class
        if aliases:
            for alias in aliases:
                cls._aliases[alias.lower()] = name.lower()
        logger.debug("Registered LLM provider: %s", name)

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseLLMProvider]]:
        """استرجاع مزود بالاسم أو الاسم المستعار."""
        key = name.lower()
        if key in cls._aliases:
            key = cls._aliases[key]
        return cls._providers.get(key)

    @classmethod
    def get_or_raise(cls, name: str) -> Type[BaseLLMProvider]:
        """استرجاع مزود أو رفع استثناء."""
        provider = cls.get(name)
        if provider is None:
            available = ", ".join(cls.list_providers())
            raise KeyError(
                f"Provider '{name}' not found. Available: {available}"
            )
        return provider

    @classmethod
    def create(cls, name: str, config: Optional[LLMConfig] = None) -> BaseLLMProvider:
        """إنشاء instance من مزود باسمه."""
        provider_class = cls.get_or_raise(name)
        cfg = config or LLMConfig(provider=name)
        return provider_class(cfg)

    @classmethod
    def list_providers(cls) -> List[str]:
        """قائمة بجميع المزودين المسجلين."""
        return sorted(cls._providers.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """هل المزود مسجل؟"""
        key = name.lower()
        return key in cls._providers or key in cls._aliases

    @classmethod
    def load_from_module(cls, module_path: str, class_name: str,
                         provider_name: str) -> bool:
        """
        تحميل ديناميكي لمزود من module path.

        مثال:
            registry.load_from_module(
                "core.llm.providers.openai_provider",
                "OpenAIProvider",
                "openai"
            )
        """
        try:
            module = importlib.import_module(module_path)
            provider_class = getattr(module, class_name)
            cls.register(provider_name, provider_class)
            return True
        except (ImportError, AttributeError) as e:
            logger.warning(
                "Failed to load provider '%s' from '%s': %s",
                provider_name, module_path, e
            )
            return False

    @classmethod
    def auto_register_defaults(cls) -> None:
        """تسجيل تلقائي للمزودين الافتراضيين."""
        default_providers = [
            ("hajeen_platform.core.llm.providers.mock_provider", "MockProvider", "mock", ["test", "fake"]),
            ("hajeen_platform.core.llm.providers.openai_provider", "OpenAIProvider", "openai", ["gpt", "chatgpt"]),
            ("hajeen_platform.core.llm.providers.huggingface_provider", "HuggingFaceProvider", "huggingface", ["hf"]),
            ("hajeen_platform.core.llm.providers.ollama_provider", "OllamaProvider", "ollama", ["local"]),
            ("hajeen_platform.core.llm.providers.llama_cpp_provider", "LlamaCppProvider", "llama_cpp", ["llama", "gguf"]),
            ("hajeen_platform.core.llm.providers.hajeen_provider", "HajeenLLMProvider", "hajeen", ["hajeen_local"]),
        ]
        for module_path, class_name, name, aliases in default_providers:
            try:
                module = importlib.import_module(module_path)
                provider_class = getattr(module, class_name)
                cls.register(name, provider_class, aliases=aliases)


            except (ImportError, AttributeError) as e:
                logger.debug("Skipped auto-registering %s: %s", name, e)



    @classmethod
    def clear(cls) -> None:
        """مسح جميع المزودين (للاختبار فقط)."""
        cls._providers.clear()
        cls._aliases.clear()
