"""
Brain Request Contract
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .base import BaseContract, RequestType, RequestPriority


@dataclass
class BrainRequestContext(BaseContract):
    """Context information for a brain request"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_history: list = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    system_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainRequest(BaseContract):
    """
    Input contract for Brain processing.
    
    This is the entry point for all requests to the Hajeen Brain.
    """
    user_message: str
    session_id: str
    user_id: Optional[str] = None
    request_type: RequestType = RequestType.CHAT
    priority: RequestPriority = RequestPriority.NORMAL
    stream: bool = False
    force_model: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.7
    context: Optional[BrainRequestContext] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.context is None:
            self.context = BrainRequestContext(
                session_id=self.session_id,
                user_id=self.user_id
            )
