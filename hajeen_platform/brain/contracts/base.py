"""
Base Contracts - Common types for all contracts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class RequestType(str, Enum):
    """Request types for Brain"""
    CHAT = "chat"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    CODE_GENERATION = "code_generation"
    QUESTION_ANSWERING = "question_answering"
    CREATIVE = "creative"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"


class RequestPriority(str, Enum):
    """Priority levels for requests"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ResponseStatus(str, Enum):
    """Response status codes"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


@dataclass(kw_only=True)
class BaseContract:
    """Base contract with common fields"""
    contract_id: str = ""
    created_at: float = 0.0
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.contract_id:
            self.contract_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now().timestamp()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, list) and value and hasattr(value[0], 'to_dict'):
                result[key] = [v.to_dict() if hasattr(v, 'to_dict') else v for v in value]
            elif hasattr(value, 'to_dict'):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result
