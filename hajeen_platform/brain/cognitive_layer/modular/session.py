"""
Reasoning Session Layer
======================

Manages reasoning sessions across multiple operations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


@dataclass
class ReasoningSession:
    """Represents a reasoning session."""
    session_id: str
    user_id: Optional[str] = None
    
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    is_active: bool = True
    
    reasoning_ids: List[str] = field(default_factory=list)
    current_reasoning_id: Optional[str] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    total_reasoning: int = 0
    successful_reasoning: int = 0
    failed_reasoning: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "is_active": self.is_active,
            "total_reasoning": self.total_reasoning,
            "successful_reasoning": self.successful_reasoning,
            "failed_reasoning": self.failed_reasoning,
            "metadata": self.metadata,
        }
    
    def record_reasoning(self, reasoning_id: str, success: bool) -> None:
        self.reasoning_ids.append(reasoning_id)
        self.current_reasoning_id = reasoning_id
        self.last_activity = time.time()
        self.total_reasoning += 1
        
        if success:
            self.successful_reasoning += 1
        else:
            self.failed_reasoning += 1
    
    @property
    def success_rate(self) -> float:
        if self.total_reasoning == 0:
            return 0.0
        return self.successful_reasoning / self.total_reasoning


class SessionManager(BaseLayer):
    """Session Manager Layer."""
    
    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        session_timeout: float = 3600.0,
        max_sessions: int = 1000,
    ):
        super().__init__(config or LayerConfig(
            name="SessionManager",
            layer_type=LayerType.SESSION,
        ))
        self.session_timeout = session_timeout
        self.max_sessions = max_sessions
        self._sessions: Dict[str, ReasoningSession] = {}
        self._default_session: Optional[ReasoningSession] = None
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.SESSION
    
    async def initialize(self) -> None:
        self._default_session = self._create_session()
        self._initialized = True
    
    def _create_session(self, user_id: Optional[str] = None) -> ReasoningSession:
        session_id = str(uuid4())[:8]
        session = ReasoningSession(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = session
        return session
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            operation = input_data.get("operation", "get_or_create")
            
            if operation == "create":
                user_id = input_data.get("user_id")
                session = self._create_session(user_id)
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=True,
                    data={"session": session.to_dict()},
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            elif operation == "record":
                session_id = input_data.get("session_id")
                reasoning_id = input_data.get("reasoning_id")
                success = input_data.get("success", True)
                
                session = self._sessions.get(session_id) or self._default_session
                if session:
                    session.record_reasoning(reasoning_id, success)
                
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=True,
                    data={"session": session.to_dict()},
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            else:  # "get_or_create"
                session_id = input_data.get("session_id")
                
                if session_id and session_id in self._sessions:
                    session = self._sessions[session_id]
                else:
                    session = self._default_session or self._create_session()
                
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=True,
                    data={"session": session.to_dict()},
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
    
    def get_session(self, session_id: str) -> Optional[ReasoningSession]:
        return self._sessions.get(session_id)
    
    def get_default_session(self) -> ReasoningSession:
        return self._default_session or self._create_session()
    
    async def cleanup(self) -> None:
        self._sessions.clear()
        self._default_session = None
        await super().cleanup()
