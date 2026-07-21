"""
Reasoning State Layer
====================

State machine for reasoning operations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


class ReasoningState(str, Enum):
    """States in the reasoning lifecycle."""
    INITIAL = "initial"
    CONTEXT_BUILT = "context_built"
    STRATEGY_SELECTED = "strategy_selected"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


STATE_TRANSITIONS: Dict[ReasoningState, List[ReasoningState]] = {
    ReasoningState.INITIAL: [ReasoningState.CONTEXT_BUILT, ReasoningState.FAILED, ReasoningState.CANCELLED],
    ReasoningState.CONTEXT_BUILT: [ReasoningState.STRATEGY_SELECTED, ReasoningState.FAILED, ReasoningState.CANCELLED],
    ReasoningState.STRATEGY_SELECTED: [ReasoningState.EXECUTING, ReasoningState.FAILED, ReasoningState.CANCELLED],
    ReasoningState.EXECUTING: [ReasoningState.VERIFYING, ReasoningState.COMPLETED, ReasoningState.FAILED, ReasoningState.CANCELLED],
    ReasoningState.VERIFYING: [ReasoningState.REFLECTING, ReasoningState.COMPLETED, ReasoningState.EXECUTING, ReasoningState.FAILED],
    ReasoningState.REFLECTING: [ReasoningState.COMPLETED, ReasoningState.EXECUTING, ReasoningState.FAILED],
    ReasoningState.COMPLETED: [],
    ReasoningState.FAILED: [ReasoningState.INITIAL],
    ReasoningState.CANCELLED: [ReasoningState.INITIAL],
}


@dataclass
class StateTransition:
    """Represents a state transition."""
    from_state: ReasoningState
    to_state: ReasoningState
    timestamp: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningStateSnapshot:
    """Snapshot of reasoning state."""
    reasoning_id: str
    current_state: ReasoningState
    previous_state: Optional[ReasoningState]
    created_at: float
    updated_at: float
    transitions: List[StateTransition] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "reasoning_id": self.reasoning_id,
            "current_state": self.current_state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "transition_count": len(self.transitions),
            "metadata": self.metadata,
        }


class ReasoningStateMachine:
    """State machine for managing reasoning state transitions."""
    
    def __init__(self, reasoning_id: str):
        self.reasoning_id = reasoning_id
        self._current_state = ReasoningState.INITIAL
        self._previous_state: Optional[ReasoningState] = None
        self._created_at = time.time()
        self._updated_at = time.time()
        self._transitions: List[StateTransition] = []
        self._callbacks: Dict[ReasoningState, List[Callable]] = {}
    
    @property
    def current_state(self) -> ReasoningState:
        return self._current_state
    
    @property
    def previous_state(self) -> Optional[ReasoningState]:
        return self._previous_state
    
    @property
    def snapshot(self) -> ReasoningStateSnapshot:
        return ReasoningStateSnapshot(
            reasoning_id=self.reasoning_id,
            current_state=self._current_state,
            previous_state=self._previous_state,
            created_at=self._created_at,
            updated_at=self._updated_at,
            transitions=self._transitions.copy(),
        )
    
    def register_callback(self, state: ReasoningState, callback: Callable) -> None:
        if state not in self._callbacks:
            self._callbacks[state] = []
        self._callbacks[state].append(callback)
    
    def can_transition(self, to_state: ReasoningState) -> bool:
        valid_next_states = STATE_TRANSITIONS.get(self._current_state, [])
        return to_state in valid_next_states
    
    def transition(
        self,
        to_state: ReasoningState,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not self.can_transition(to_state):
            return False
        
        transition = StateTransition(
            from_state=self._current_state,
            to_state=to_state,
            timestamp=time.time(),
            reason=reason,
            metadata=metadata or {},
        )
        self._transitions.append(transition)
        
        self._previous_state = self._current_state
        self._current_state = to_state
        self._updated_at = time.time()
        
        self._execute_callbacks(to_state)
        
        return True
    
    def _execute_callbacks(self, state: ReasoningState) -> None:
        callbacks = self._callbacks.get(state, [])
        for callback in callbacks:
            try:
                callback(self)
            except Exception:
                pass


class ReasoningStateLayer(BaseLayer):
    """Reasoning State Layer."""
    
    def __init__(self, config: Optional[LayerConfig] = None):
        super().__init__(config or LayerConfig(
            name="ReasoningStateLayer",
            layer_type=LayerType.STATE,
        ))
        self._state_machines: Dict[str, ReasoningStateMachine] = {}
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.STATE
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            operation = input_data.get("operation", "transition")
            reasoning_id = input_data.get("reasoning_id")
            
            if operation == "create":
                machine = ReasoningStateMachine(reasoning_id)
                self._state_machines[reasoning_id] = machine
                
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=True,
                    data={"state": machine.snapshot.to_dict()},
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            elif operation == "transition":
                to_state = ReasoningState(input_data.get("to_state"))
                reason = input_data.get("reason", "")
                metadata = input_data.get("metadata", {})
                
                machine = self._state_machines.get(reasoning_id)
                if not machine:
                    return LayerResult(
                        layer_name=self.name,
                        layer_type=self.layer_type,
                        success=False,
                        error=f"State machine not found: {reasoning_id}",
                        execution_time_ms=(time.perf_counter() - start_time) * 1000,
                    )
                
                success = machine.transition(to_state, reason, metadata)
                
                if not success:
                    return LayerResult(
                        layer_name=self.name,
                        layer_type=self.layer_type,
                        success=False,
                        error=f"Invalid transition from {machine.current_state.value} to {to_state.value}",
                        data={"current_state": machine.current_state.value},
                        execution_time_ms=(time.perf_counter() - start_time) * 1000,
                    )
                
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=True,
                    data={
                        "state": machine.snapshot.to_dict(),
                        "transition": {
                            "from": machine.previous_state.value if machine.previous_state else None,
                            "to": machine.current_state.value,
                        },
                    },
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            else:
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=False,
                    error=f"Unknown operation: {operation}",
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
    
    def get_state_machine(self, reasoning_id: str) -> Optional[ReasoningStateMachine]:
        return self._state_machines.get(reasoning_id)
    
    async def cleanup(self) -> None:
        self._state_machines.clear()
        await super().cleanup()
