"""
Decision Contract - Interface for Decision Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base import BaseContract


class DecisionType(str, Enum):
    """Types of decisions"""
    MODEL_SELECTION = "model_selection"
    RESOURCE_ALLOCATION = "resource_allocation"
    EXECUTION_STRATEGY = "execution_strategy"
    RETRY_DECISION = "retry_decision"


@dataclass
class ModelSelection(BaseContract):
    """Model selection decision"""
    primary_model: str
    fallback_models: List[str] = field(default_factory=list)
    
    # Model properties
    quality_score: float = 0.0
    speed_score: float = 0.0
    cost_score: float = 0.0
    
    # Reasoning
    confidence: float = 0.0
    reasoning: str = ""
    alternatives: List[str] = field(default_factory=list)


@dataclass
class ResourceAllocation(BaseContract):
    """Resource allocation decision"""
    # Resources
    use_rag: bool = False
    use_web_search: bool = False
    use_multi_model: bool = False
    
    # Retry strategy
    retry_strategy: str = "none"
    max_retries: int = 3
    
    # Parallel execution
    parallel_limit: int = 1
    execution_order: str = "sequential"


@dataclass
class DecisionResult(BaseContract):
    """
    Output from Decision Engine.
    
    This contract is passed from DecisionEngine to ModelRouter.
    """
    success: bool
    
    # Decision type
    decision_type: DecisionType = DecisionType.MODEL_SELECTION
    
    # Model selection
    model_selection: Optional[ModelSelection] = None
    
    # Resource allocation
    resource_allocation: Optional[ResourceAllocation] = None
    
    # Metadata
    confidence: float = 0.0
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    
    # Errors
    errors: List[str] = field(default_factory=list)
