"""
Reasoning Context Layer
======================

Manages context for reasoning operations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType
from brain.cognitive_layer.modular.strategy import ReasoningStrategy


@dataclass
class ReasoningContext:
    """Immutable context for a reasoning operation."""
    reasoning_id: str
    problem: str
    strategy: ReasoningStrategy
    
    input_context: Dict[str, Any] = field(default_factory=dict)
    enriched_context: Dict[str, Any] = field(default_factory=dict)
    
    created_at: float = field(default_factory=time.time)
    max_length: int = 10000
    
    trace_enabled: bool = True
    trace_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "reasoning_id": self.reasoning_id,
            "problem": self.problem,
            "strategy": self.strategy.value,
            "input_context": self.input_context,
            "enriched_context": self.enriched_context,
            "created_at": self.created_at,
            "trace_enabled": self.trace_enabled,
            "trace_id": self.trace_id,
        }


class ContextBuilder:
    """Builder for ReasoningContext."""
    
    def __init__(self, reasoning_id: str, problem: str, strategy: ReasoningStrategy):
        self._context = ReasoningContext(
            reasoning_id=reasoning_id,
            problem=problem,
            strategy=strategy,
        )
    
    def with_input_context(self, context: Dict[str, Any]) -> ContextBuilder:
        self._context.input_context = context
        return self
    
    def with_trace(self, enabled: bool, trace_id: Optional[str] = None) -> ContextBuilder:
        self._context.trace_enabled = enabled
        self._context.trace_id = trace_id
        return self
    
    def with_max_length(self, max_length: int) -> ContextBuilder:
        self._context.max_length = max_length
        return self
    
    def with_enrichment(self, enrichment: Dict[str, Any]) -> ContextBuilder:
        self._context.enriched_context.update(enrichment)
        return self
    
    def build(self) -> ReasoningContext:
        return self._context


class ContextManager(BaseLayer):
    """
    Context Manager Layer.
    
    Responsible for building, validating, and enriching context.
    """
    
    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        max_context_length: int = 10000,
    ):
        super().__init__(config or LayerConfig(
            name="ContextManager",
            layer_type=LayerType.CONTEXT,
        ))
        self.max_context_length = max_context_length
        self._active_contexts: Dict[str, ReasoningContext] = {}
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.CONTEXT
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            reasoning_id = input_data.get("reasoning_id")
            problem = input_data.get("problem", "")
            strategy = ReasoningStrategy(input_data.get("strategy", "chain_of_thought"))
            raw_context = input_data.get("context", {})
            
            if not problem or not problem.strip():
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=False,
                    error="Problem cannot be empty",
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            builder = ContextBuilder(reasoning_id, problem, strategy)
            context = (
                builder
                .with_input_context(raw_context)
                .with_trace(input_data.get("enable_trace", True))
                .with_max_length(self.max_context_length)
                .build()
            )
            
            validation_result = self._validate_context(context)
            if not validation_result["valid"]:
                return LayerResult(
                    layer_name=self.name,
                    layer_type=self.layer_type,
                    success=False,
                    error=validation_result["error"],
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            enriched = self._enrich_context(context)
            context.enriched_context = enriched
            
            self._active_contexts[reasoning_id] = context
            
            return LayerResult(
                layer_name=self.name,
                layer_type=self.layer_type,
                success=True,
                data={
                    "context": context.to_dict(),
                    "enrichments": list(enriched.keys()),
                },
                warnings=validation_result.get("warnings", []),
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
    
    def _validate_context(self, context: ReasoningContext) -> Dict[str, Any]:
        warnings = []
        
        if len(context.problem) > context.max_length:
            return {
                "valid": False,
                "error": f"Problem exceeds maximum length ({context.max_length})",
                "warnings": warnings,
            }
        
        if len(context.problem) < 10:
            warnings.append("Problem is very short, may not provide enough context")
        
        return {"valid": True, "warnings": warnings}
    
    def _enrich_context(self, context: ReasoningContext) -> Dict[str, Any]:
        enrichment = {}
        enrichment["problem_length"] = len(context.problem)
        enrichment["word_count"] = len(context.problem.split())
        enrichment["strategy_name"] = context.strategy.value
        enrichment.update(context.input_context)
        return enrichment
    
    def get_context(self, reasoning_id: str) -> Optional[ReasoningContext]:
        return self._active_contexts.get(reasoning_id)
    
    async def cleanup(self) -> None:
        self._active_contexts.clear()
        await super().cleanup()
