"""
Hajeen Brain Contracts - Shared Data Models
===========================================

This module defines the contract interfaces between brain components.
These contracts ensure type safety and clear data flow between engines.

Contracts:
- BrainRequest: Input to the brain
- BrainResponse: Output from the brain
- ReasoningResult: Output from ReasoningEngine
- PlanningResult: Output from PlanningEngine
- DecisionResult: Output from DecisionEngine
- ExecutionResult: Output from ModelRouter/Executor
"""

from .base import (
    BaseContract,
    RequestType,
    RequestPriority,
    ResponseStatus,
)

from .brain_request import BrainRequest, BrainRequestContext
from .brain_response import BrainResponse, ExecutionMetadata
from .reasoning_contract import ReasoningResult, ReasoningStrategy
from .planning_contract import PlanningResult, ExecutionPlan, Task
from .decision_contract import DecisionResult, ModelSelection
from .execution_contract import ExecutionResult, TokenUsage

__all__ = [
    # Base
    "BaseContract",
    "RequestType",
    "RequestPriority",
    "ResponseStatus",
    
    # Brain
    "BrainRequest",
    "BrainRequestContext",
    "BrainResponse",
    "ExecutionMetadata",
    
    # Reasoning
    "ReasoningResult",
    "ReasoningStrategy",
    
    # Planning
    "PlanningResult",
    "ExecutionPlan",
    "Task",
    
    # Decision
    "DecisionResult",
    "ModelSelection",
    
    # Execution
    "ExecutionResult",
    "TokenUsage",
]
