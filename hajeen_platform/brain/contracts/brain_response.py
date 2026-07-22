"""
Brain Response Contract
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseContract, ResponseStatus


@dataclass
class ExecutionMetadata(BaseContract):
    """Metadata about the execution flow"""
    total_latency_ms: float = 0.0
    engine_latencies: Dict[str, float] = field(default_factory=dict)
    tokens_used: int = 0
    model_used: str = ""
    cache_hit: bool = False


@dataclass
class BrainResponse(BaseContract):
    """
    Output contract from Brain processing.
    
    This is the final response returned to the user.
    """
    content: str
    session_id: str
    
    # Status
    status: ResponseStatus = ResponseStatus.SUCCESS
    
    # Execution info
    execution_metadata: ExecutionMetadata = None
    
    # Intent/analysis info
    intent: Optional[str] = None
    confidence: float = 0.0
    reasoning_steps: List[Dict[str, Any]] = field(default_factory=list)
    
    # Model info
    model_used: str = ""
    fallback_used: bool = False
    
    # Error info
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Extra data
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.execution_metadata is None:
            self.execution_metadata = ExecutionMetadata()
