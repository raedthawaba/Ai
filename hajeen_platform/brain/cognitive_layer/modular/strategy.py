"""
Strategy Selector Layer
======================

Plugin-based strategy selection system for the Reasoning Engine.
Supports adding new strategies via Registry without modifying the engine.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


class ReasoningStrategy(str, Enum):
    """Available reasoning strategies."""
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    DECOMPOSITION = "decomposition"
    ANALOGY = "analogy"
    FIRST_PRINCIPLES = "first_principles"
    MULTI_PERSPECTIVE = "multi_perspective"
    DEFAULT = "chain_of_thought"
    
    @classmethod
    def from_string(cls, value: str) -> ReasoningStrategy:
        """Create strategy from string."""
        try:
            return cls(value)
        except ValueError:
            return cls.DEFAULT


class StrategyMetadata(BaseModel):
    """Metadata for a reasoning strategy."""
    name: str
    description: str
    best_for: List[str] = Field(default_factory=list)
    complexity: str = "medium"
    requires_context: bool = False


@dataclass
class StrategySelectionContext:
    """Context for strategy selection."""
    problem: str
    context: Dict[str, Any]
    previous_strategies: List[ReasoningStrategy] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    user_preference: Optional[ReasoningStrategy] = None


@dataclass
class StrategySelectionResult:
    """Result of strategy selection."""
    selected_strategy: ReasoningStrategy
    confidence: float
    reasoning: str
    alternatives: List[ReasoningStrategy] = field(default_factory=list)


class BaseStrategy(ABC):
    """Abstract base class for reasoning strategies."""
    
    def __init__(self, name: ReasoningStrategy):
        self.name = name
        self._execution_count = 0
        self._success_count = 0
    
    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""
        pass
    
    @abstractmethod
    async def execute(
        self,
        problem: str,
        context: Dict[str, Any],
        llm_manager: Any,
        config: Any,
    ) -> List[Dict[str, Any]]:
        """Execute the reasoning strategy."""
        pass
    
    def record_execution(self, success: bool) -> None:
        """Record execution result."""
        self._execution_count += 1
        if success:
            self._success_count += 1


class StrategyRegistry:
    """Registry for reasoning strategies with plugin support."""
    
    _instance: Optional[StrategyRegistry] = None
    
    def __init__(self):
        self._strategies: Dict[ReasoningStrategy, BaseStrategy] = {}
        self._plugins: Dict[str, type] = {}
    
    @classmethod
    def get_instance(cls) -> StrategyRegistry:
        if cls._instance is None:
            cls._instance = StrategyRegistry()
        return cls._instance
    
    def register(self, strategy: ReasoningStrategy, implementation: BaseStrategy) -> None:
        self._strategies[strategy] = implementation
    
    def register_plugin(self, name: str, strategy_class: type) -> None:
        self._plugins[name] = strategy_class
    
    def get(self, strategy: ReasoningStrategy) -> Optional[BaseStrategy]:
        return self._strategies.get(strategy)
    
    def get_all(self) -> Dict[ReasoningStrategy, BaseStrategy]:
        return dict(self._strategies)
    
    def list_available(self) -> List[ReasoningStrategy]:
        return list(self._strategies.keys())
    
    def clear(self) -> None:
        self._strategies.clear()
        self._plugins.clear()


class StrategySelector(BaseLayer):
    """
    Strategy Selector Layer.
    
    Responsible for selecting the most appropriate reasoning strategy
    based on the problem context.
    """
    
    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        registry: Optional[StrategyRegistry] = None,
        default_strategy: ReasoningStrategy = ReasoningStrategy.CHAIN_OF_THOUGHT,
    ):
        super().__init__(config or LayerConfig(
            name="StrategySelector",
            layer_type=LayerType.STRATEGY_SELECTOR,
        ))
        self.registry = registry or StrategyRegistry.get_instance()
        self.default_strategy = default_strategy
        self._selection_history: List[StrategySelectionResult] = []
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.STRATEGY_SELECTOR
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            selection_context = StrategySelectionContext(
                problem=input_data.get("problem", ""),
                context=input_data.get("context", {}),
                previous_strategies=input_data.get("previous_strategies", []),
                constraints=input_data.get("constraints", {}),
                user_preference=input_data.get("user_preference"),
            )
            
            if selection_context.user_preference:
                selected = selection_context.user_preference
                confidence = 1.0
                reasoning = "User-specified strategy"
            else:
                selected, confidence, reasoning = self._select_strategy(selection_context)
            
            alternatives = self._get_alternatives(selected)
            
            result = StrategySelectionResult(
                selected_strategy=selected,
                confidence=confidence,
                reasoning=reasoning,
                alternatives=alternatives,
            )
            
            self._selection_history.append(result)
            
            return LayerResult(
                layer_name=self.name,
                layer_type=self.layer_type,
                success=True,
                data={
                    "selected_strategy": selected.value,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "alternatives": [a.value for a in alternatives],
                },
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )
            
        except Exception as e:
            return LayerResult(
                layer_name=self.name,
                layer_type=self.layer_type,
                success=False,
                error=str(e),
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )
    
    def _select_strategy(self, context: StrategySelectionContext) -> tuple:
        """Select the best strategy based on context."""
        problem = context.problem.lower()
        
        if any(word in problem for word in ["分解", "تفكيك", "decompose", "break down"]):
            return ReasoningStrategy.DECOMPOSITION, 0.9, "Problem contains decomposition keywords"
        
        if any(word in problem for word in ["类似", "analogy", "مثيل", "مثل"]):
            return ReasoningStrategy.ANALOGY, 0.85, "Problem suggests analogical reasoning"
        
        if any(word in problem for word in ["原则", "principles", "مبادئ", "أساسيات"]):
            return ReasoningStrategy.FIRST_PRINCIPLES, 0.9, "Problem requires first principles analysis"
        
        if any(word in problem for word in ["视角", "perspective", "نظرة", "角度"]):
            return ReasoningStrategy.MULTI_PERSPECTIVE, 0.85, "Problem benefits from multiple perspectives"
        
        return ReasoningStrategy.CHAIN_OF_THOUGHT, 0.7, "Default strategy selection"
    
    def _get_alternatives(self, selected: ReasoningStrategy) -> List[ReasoningStrategy]:
        all_strategies = self.registry.list_available()
        alternatives = [s for s in all_strategies if s != selected]
        return alternatives[:3]
