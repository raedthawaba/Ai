"""
Execution Contract - Interface for Model Router and Execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseContract, ResponseStatus


@dataclass
class TokenUsage(BaseContract):
    """Token usage statistics"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    # Cost
    cost_usd: float = 0.0


@dataclass
class ExecutionResult(BaseContract):
    """
    Final execution result.
    
    This contract is the final output before returning to the user.
    """
    success: bool
    content: str
    
    # Status
    status: ResponseStatus = ResponseStatus.SUCCESS
    
    # Model info
    model_used: str = ""
    response_time_ms: float = 0.0
    
    # Token usage
    token_usage: TokenUsage = None
    
    # Quality metrics
    quality_score: float = 0.0
    confidence: float = 0.0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.token_usage is None:
            self.token_usage = TokenUsage()
