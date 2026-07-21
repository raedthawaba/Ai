"""
Base classes for Planning Engine components.
==========================================

Implements Registry Pattern, Dependency Injection, and Plugin Architecture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field
import logging


# ============================================================================
# LOGGER SETUP
# ============================================================================

logger = logging.getLogger("planning_engine")


# ============================================================================
# BASE COMPONENT
# ============================================================================

class BaseComponent:
    """Base class for all planning engine components."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"planning_engine.{self.__class__.__name__}")
        self._initialized = False
        self._metrics: Dict[str, Any] = {}
    
    async def initialize(self) -> None:
        """Initialize the component."""
        if self._initialized:
            return
        await self._async_initialize()
        self._initialized = True
        self.logger.info(f"{self.__class__.__name__} initialized")
    
    async def _async_initialize(self) -> None:
        """Async initialization hook. Override in subclasses."""
        pass
    
    @property
    def is_initialized(self) -> bool:
        """Check if component is initialized."""
        return self._initialized
    
    def record_metric(self, name: str, value: Any) -> None:
        """Record a metric."""
        self._metrics[name] = {
            "value": value,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all recorded metrics."""
        return self._metrics.copy()


# ============================================================================
# REGISTRY PATTERN
# ============================================================================

T = TypeVar('T')


class Registry(Generic[T]):
    """Generic registry for plugin/component management."""
    
    _instance: Optional[Registry] = None
    
    def __init__(self):
        self._registry: Dict[str, Type[T]] = {}
        self._instances: Dict[str, T] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def get_instance(cls) -> Registry:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = Registry()
        return cls._instance
    
    def register(self, name: str, cls: Type[T], config: Optional[Dict[str, Any]] = None) -> None:
        """Register a component class."""
        if name in self._registry:
            raise ValueError(f"Component '{name}' already registered")
        self._registry[name] = cls
        self._configs[name] = config or {}
        logger.info(f"Registered component: {name}")
    
    def unregister(self, name: str) -> None:
        """Unregister a component."""
        if name in self._registry:
            del self._registry[name]
            if name in self._instances:
                del self._instances[name]
            if name in self._configs:
                del self._configs[name]
            logger.info(f"Unregistered component: {name}")
    
    def get_class(self, name: str) -> Type[T]:
        """Get registered class by name."""
        if name not in self._registry:
            raise KeyError(f"Component '{name}' not registered")
        return self._registry[name]
    
    def get_instance(self, name: str) -> T:
        """Get or create singleton instance."""
        if name not in self._instances:
            if name not in self._registry:
                raise KeyError(f"Component '{name}' not registered")
            config = self._configs.get(name, {})
            self._instances[name] = self._registry[name](**config)
        return self._instances[name]
    
    def create_instance(self, name: str, **kwargs) -> T:
        """Create new instance with optional overrides."""
        if name not in self._registry:
            raise KeyError(f"Component '{name}' not registered")
        config = self._configs.get(name, {})
        config.update(kwargs)
        return self._registry[name](**config)
    
    def list_registered(self) -> List[str]:
        """List all registered component names."""
        return list(self._registry.keys())
    
    def is_registered(self, name: str) -> bool:
        """Check if component is registered."""
        return name in self._registry


# ============================================================================
# PLANNING CONTEXT
# ============================================================================

class PlanningContext(BaseModel):
    """Context passed through the planning pipeline."""
    
    # Input from Reasoning Engine
    reasoning_result: Dict[str, Any] = Field(default_factory=dict)
    
    # Configuration
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # State
    current_phase: str = Field(default="init")
    phase_results: Dict[str, Any] = Field(default_factory=dict)
    
    # Components (not in original model, added dynamically)
    goal_tree: Optional[Any] = Field(default=None)
    task_graph: Optional[Any] = Field(default=None)
    execution_graph: Optional[Any] = Field(default=None)
    
    # Resources
    available_resources: Dict[str, Resource] = Field(default_factory=dict)
    
    # History
    history: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def add_result(self, phase: str, result: Any) -> None:
        """Add result from a phase."""
        self.phase_results[phase] = {
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.history.append({
            "phase": phase,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": str(result)[:100]
        })
    
    def get_result(self, phase: str) -> Optional[Any]:
        """Get result from a phase."""
        if phase in self.phase_results:
            return self.phase_results[phase]["result"]
        return None


# Import Resource for type hints
from .models import Resource


# ============================================================================
# PIPELINE STAGES
# ============================================================================

class PipelineStage(BaseComponent):
    """Base class for pipeline stages."""
    
    def __init__(self, stage_name: str):
        super().__init__()
        self.stage_name = stage_name
    
    async def execute(self, context: PlanningContext) -> PlanningContext:
        """Execute the stage."""
        raise NotImplementedError()


# ============================================================================
# PLUGIN INTERFACE
# ============================================================================

class Plugin(BaseComponent):
    """Base class for planning engine plugins."""
    
    @property
    def name(self) -> str:
        """Plugin name."""
        return self.__class__.__name__
    
    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"
    
    async def execute(self, context: PlanningContext) -> PlanningContext:
        """Execute plugin logic."""
        raise NotImplementedError()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "BaseComponent",
    "Registry",
    "PlanningContext",
    "PipelineStage",
    "Plugin",
]
