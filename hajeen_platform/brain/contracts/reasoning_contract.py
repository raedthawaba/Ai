"""
Reasoning Contract - Interface for Reasoning Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base import BaseContract


class ReasoningStrategy(str, Enum):
    """Reasoning strategies"""
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    REFLEXION = "reflexion"
    REACT = "react"
    DIRECT = "direct"
    ANALOGICAL = "analogical"
    CAUSAL = "causal"


@dataclass
class ReasoningStep(BaseContract):
    """A single step in the reasoning process"""
    step_id: str
    description: str
    reasoning: str
    conclusion: str
    confidence: float = 0.0
    alternatives: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResult(BaseContract):
    """
    Output from Reasoning Engine.
    
    This contract is passed from ReasoningEngine to PlanningEngine.
    """
    result_id: str
    strategy: ReasoningStrategy
    
    # Reasoning content
    reasoning_steps: List[ReasoningStep] = field(default_factory=list)
    recommended_solution: Any = None
    solution_options: List[Any] = field(default_factory=list)
    
    # Analysis
    missing_information: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    
    # Metrics
    confidence: float = 0.0
    complexity: str = "medium"
    estimated_tokens: int = 0
