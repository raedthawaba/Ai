"""
Modular Reasoning Engine Architecture
=====================================

A refactored, modular architecture for the Reasoning Engine with:
- Strategy Selector: Plugin-based strategy selection
- Reasoning Pipeline: Orchestration layer
- Reasoning Context: Context management
- Reasoning Session: Session management
- Reasoning State: State machine
- Confidence Engine: Confidence calculation
- Explanation Engine: Explanation generation
- Verification Layer: Result verification
- Reflection Layer: Self-reflection
"""

from brain.cognitive_layer.modular.base import (
    BaseLayer,
    LayerConfig,
    LayerResult,
    LayerType,
)
from brain.cognitive_layer.modular.context import (
    ReasoningContext,
    ContextBuilder,
    ContextManager,
)
from brain.cognitive_layer.modular.session import (
    ReasoningSession,
    SessionManager,
)
from brain.cognitive_layer.modular.state import (
    ReasoningState,
    ReasoningStateMachine,
)
from brain.cognitive_layer.modular.strategy import (
    StrategySelector,
    ReasoningStrategy,
    StrategyRegistry,
    BaseStrategy,
)
from brain.cognitive_layer.modular.pipeline import (
    ReasoningPipeline,
    PipelineStep,
    PipelineConfig,
)
from brain.cognitive_layer.modular.confidence import (
    ConfidenceEngine,
    ConfidenceResult,
)
from brain.cognitive_layer.modular.explanation import (
    ExplanationEngine,
    ExplanationResult,
)
from brain.cognitive_layer.modular.verification import (
    VerificationLayer,
    VerificationResult,
    VerificationRule,
)
from brain.cognitive_layer.modular.reflection import (
    ReflectionLayer,
    ReflectionResult,
)
from brain.cognitive_layer.modular.orchestrator import (
    ModularReasoningEngine,
    ModularReasoningResult,
    create_modular_engine,
)

__all__ = [
    # Base
    "BaseLayer",
    "LayerConfig",
    "LayerResult",
    "LayerType",
    # Context
    "ReasoningContext",
    "ContextBuilder",
    "ContextManager",
    # Session
    "ReasoningSession",
    "SessionManager",
    # State
    "ReasoningState",
    "ReasoningStateMachine",
    # Strategy
    "StrategySelector",
    "ReasoningStrategy",
    "StrategyRegistry",
    "BaseStrategy",
    # Pipeline
    "ReasoningPipeline",
    "PipelineStep",
    "PipelineConfig",
    # Confidence
    "ConfidenceEngine",
    "ConfidenceResult",
    # Explanation
    "ExplanationEngine",
    "ExplanationResult",
    # Verification
    "VerificationLayer",
    "VerificationResult",
    "VerificationRule",
    # Reflection
    "ReflectionLayer",
    "ReflectionResult",
    # Orchestrator
    "ModularReasoningEngine",
    "ModularReasoningResult",
    "create_modular_engine",
]
