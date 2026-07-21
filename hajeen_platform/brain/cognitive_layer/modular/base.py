"""
Base Layer Interfaces
====================

Defines the base interfaces and data structures for all modular layers.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LayerType(str, Enum):
    """Types of layers in the modular architecture."""
    STRATEGY_SELECTOR = "strategy_selector"
    CONTEXT = "context"
    SESSION = "session"
    STATE = "state"
    PIPELINE = "pipeline"
    CONFIDENCE = "confidence"
    EXPLANATION = "explanation"
    VERIFICATION = "verification"
    REFLECTION = "reflection"
    ORCHESTRATOR = "orchestrator"


@dataclass
class LayerConfig:
    """Configuration for a layer."""
    name: str
    layer_type: LayerType
    enabled: bool = True
    timeout_seconds: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "layer_type": self.layer_type.value,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }


@dataclass
class LayerResult:
    """Result from a layer execution."""
    layer_name: str
    layer_type: LayerType
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        """Check if the result is valid."""
        return self.success and self.error is None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_name": self.layer_name,
            "layer_type": self.layer_type.value,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "warnings": self.warnings,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


class BaseLayer(ABC):
    """
    Abstract base class for all modular layers.
    
    Each layer must implement:
    - initialize(): Set up the layer
    - execute(): Run the layer's main logic
    - cleanup(): Clean up resources
    """
    
    def __init__(self, config: LayerConfig):
        self.config = config
        self._initialized = False
        self._execution_count = 0
        self._total_execution_time = 0.0
    
    @property
    @abstractmethod
    def layer_type(self) -> LayerType:
        """Return the type of this layer."""
        pass
    
    @property
    def name(self) -> str:
        """Return the name of this layer."""
        return self.config.name
    
    @property
    def is_initialized(self) -> bool:
        """Check if the layer is initialized."""
        return self._initialized
    
    @property
    def statistics(self) -> Dict[str, Any]:
        """Return execution statistics."""
        avg_time = (
            self._total_execution_time / self._execution_count 
            if self._execution_count > 0 else 0.0
        )
        return {
            "name": self.name,
            "layer_type": self.layer_type.value,
            "initialized": self._initialized,
            "execution_count": self._execution_count,
            "total_execution_time_ms": round(self._total_execution_time, 2),
            "avg_execution_time_ms": round(avg_time, 2),
        }
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the layer."""
        pass
    
    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        """Execute the layer's main logic."""
        pass
    
    async def cleanup(self) -> None:
        """Clean up layer resources."""
        self._initialized = False


class LayerRegistry:
    """Registry for managing layer instances."""
    
    _instance: Optional[LayerRegistry] = None
    
    def __init__(self):
        self._layers: Dict[LayerType, BaseLayer] = {}
        self._layer_factories: Dict[LayerType, type] = {}
        self._dependencies: Dict[LayerType, List[LayerType]] = {}
    
    @classmethod
    def get_instance(cls) -> LayerRegistry:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = LayerRegistry()
        return cls._instance
    
    def register_layer(self, layer_type: LayerType, factory: type) -> None:
        """Register a layer factory."""
        self._layer_factories[layer_type] = factory
    
    def register_dependency(self, layer_type: LayerType, depends_on: List[LayerType]) -> None:
        """Register dependencies for a layer."""
        self._dependencies[layer_type] = depends_on
    
    def add_layer(self, layer_type: LayerType, layer: BaseLayer) -> None:
        """Add a layer instance."""
        self._layers[layer_type] = layer
    
    def get_layer(self, layer_type: LayerType) -> Optional[BaseLayer]:
        """Get a layer instance."""
        return self._layers.get(layer_type)
    
    def get_all_layers(self) -> Dict[LayerType, BaseLayer]:
        """Get all registered layers."""
        return dict(self._layers)
    
    def get_dependencies(self, layer_type: LayerType) -> List[LayerType]:
        """Get dependencies for a layer type."""
        return self._dependencies.get(layer_type, [])
    
    def clear(self) -> None:
        """Clear all registered layers."""
        self._layers.clear()
        self._layer_factories.clear()
        self._dependencies.clear()
