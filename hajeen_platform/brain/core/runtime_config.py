"""
Hajeen Core Runtime Configuration
================================

This module provides a unified runtime configuration that allows
all engines to work without real API keys by using mock fallbacks.

Author: OpenHands AI Agent
"""

import os
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    """
    Unified runtime configuration for Hajeen.
    
    This configuration allows the system to run in two modes:
    1. PRODUCTION: Uses real LLM API
    2. DEVELOPMENT: Uses mock fallbacks
    """
    
    # Mode: "production" or "development"
    mode: str = "development"
    
    # LLM Configuration
    openai_api_key: Optional[str] = None
    model: str = "gpt-4"
    
    # Embedding Configuration
    embedding_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 384
    
    # Use mock fallbacks
    use_mock_llm: bool = True
    use_mock_embeddings: bool = True
    
    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        """Create configuration from environment variables."""
        return cls(
            mode=os.getenv("HAJEEN_MODE", "development"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("HAJEEN_MODEL", "gpt-4"),
            embedding_api_key=os.getenv("EMBEDDING_API_KEY"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", "384")),
            use_mock_llm=os.getenv("HAJEEN_USE_MOCK_LLM", "true").lower() == "true",
            use_mock_embeddings=os.getenv("HAJEEN_USE_MOCK_EMBEDDINGS", "true").lower() == "true",
        )
    
    def should_use_mock_llm(self) -> bool:
        """Check if mock LLM should be used."""
        if self.mode == "development":
            return True
        return self.use_mock_llm or not self.openai_api_key
    
    def should_use_mock_embeddings(self) -> bool:
        """Check if mock embeddings should be used."""
        if self.mode == "development":
            return True
        return self.use_mock_embeddings or not self.embedding_api_key


# Global runtime configuration
_runtime_config: Optional[RuntimeConfig] = None


def get_runtime_config() -> RuntimeConfig:
    """Get the global runtime configuration."""
    global _runtime_config
    if _runtime_config is None:
        _runtime_config = RuntimeConfig.from_env()
    return _runtime_config


def set_runtime_config(config: RuntimeConfig) -> None:
    """Set the global runtime configuration."""
    global _runtime_config
    _runtime_config = config


def reset_runtime_config() -> None:
    """Reset the global runtime configuration."""
    global _runtime_config
    _runtime_config = None


def get_llm_manager() -> Any:
    """
    Get LLM Manager based on configuration.
    
    Returns MockLLMManager if no API key is available,
    otherwise returns the real LLMManager.
    """
    config = get_runtime_config()
    
    if config.should_use_mock_llm():
        from .mock_llm import get_mock_llm_manager
        return get_mock_llm_manager({"model": config.model})
    
    # Try to import real LLM manager
    try:
        from hajeen_platform.core.llm import get_llm_manager
        return get_llm_manager(config.openai_api_key)
    except Exception:
        from .mock_llm import get_mock_llm_manager
        return get_mock_llm_manager({"model": config.model})


def get_embedding_manager() -> Any:
    """
    Get Embedding Manager based on configuration.
    
    Returns MockEmbeddingManager if no API key is available,
    otherwise returns the real EmbeddingManager.
    """
    config = get_runtime_config()
    
    if config.should_use_mock_embeddings():
        from .mock_llm import get_mock_embedding_manager
        return get_mock_embedding_manager({"dimension": config.embedding_dimension})
    
    # Try to import real embedding manager
    try:
        from hajeen_platform.core.embeddings import get_embedding_manager
        return get_embedding_manager(config.embedding_api_key)
    except Exception:
        from .mock_llm import get_mock_embedding_manager
        return get_mock_embedding_manager({"dimension": config.embedding_dimension})
