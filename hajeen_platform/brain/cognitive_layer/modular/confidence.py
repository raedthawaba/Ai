"""
Confidence Engine Layer
======================

Calculates confidence scores for reasoning results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


@dataclass
class ConfidenceScore:
    """Individual confidence score component."""
    name: str
    value: float
    weight: float
    reason: str


@dataclass
class ConfidenceResult:
    """Result of confidence calculation."""
    overall_confidence: float
    scores: List[ConfidenceScore]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_confidence": self.overall_confidence,
            "scores": [
                {"name": s.name, "value": s.value, "weight": s.weight, "reason": s.reason}
                for s in self.scores
            ],
            "metadata": self.metadata,
        }


class ConfidenceEngine(BaseLayer):
    """Confidence Engine Layer."""
    
    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        fallback_confidence: float = 0.3,
    ):
        super().__init__(config or LayerConfig(
            name="ConfidenceEngine",
            layer_type=LayerType.CONFIDENCE,
        ))
        self.fallback_confidence = fallback_confidence
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.CONFIDENCE
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            reasoning_steps = input_data.get("reasoning_steps", [])
            solutions = input_data.get("solutions", [])
            risks = input_data.get("risks", [])
            
            scores = []
            
            step_score = self._calculate_step_confidence(reasoning_steps)
            scores.append(step_score)
            
            solution_score = self._calculate_solution_confidence(solutions)
            scores.append(solution_score)
            
            risk_adjustment = self._calculate_risk_adjustment(risks)
            
            overall = self._calculate_overall(scores, risk_adjustment)
            
            result = ConfidenceResult(
                overall_confidence=overall,
                scores=scores,
                metadata={
                    "step_count": len(reasoning_steps),
                    "solution_count": len(solutions),
                    "risk_count": len(risks),
                },
            )
            
            return LayerResult(
                layer_name=self.name,
                layer_type=self.layer_type,
                success=True,
                data=result.to_dict(),
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
    
    def _calculate_step_confidence(self, steps: List[Dict[str, Any]]) -> ConfidenceScore:
        if not steps:
            return ConfidenceScore(
                name="step_confidence",
                value=self.fallback_confidence,
                weight=0.4,
                reason="No reasoning steps available",
            )
        
        total_confidence = sum(s.get("confidence", 0.5) for s in steps)
        avg_confidence = total_confidence / len(steps)
        
        if len(steps) < 3:
            avg_confidence *= 0.8
        
        return ConfidenceScore(
            name="step_confidence",
            value=min(1.0, max(0.0, avg_confidence)),
            weight=0.4,
            reason=f"Based on {len(steps)} reasoning steps",
        )
    
    def _calculate_solution_confidence(self, solutions: List[Dict[str, Any]]) -> ConfidenceScore:
        if not solutions:
            return ConfidenceScore(
                name="solution_confidence",
                value=self.fallback_confidence,
                weight=0.3,
                reason="No solutions proposed",
            )
        
        recommended = next((s for s in solutions if s.get("recommended", False)), None)
        if recommended:
            feasibility = recommended.get("feasibility_score", 0.5)
        else:
            feasibility = sum(s.get("feasibility_score", 0.5) for s in solutions) / len(solutions)
        
        return ConfidenceScore(
            name="solution_confidence",
            value=min(1.0, max(0.0, feasibility)),
            weight=0.3,
            reason=f"Based on {len(solutions)} solution options",
        )
    
    def _calculate_risk_adjustment(self, risks: List[Dict[str, Any]]) -> float:
        if not risks:
            return 1.0
        
        critical_count = sum(1 for r in risks if r.get("severity") == "critical")
        high_count = sum(1 for r in risks if r.get("severity") == "high")
        
        penalty = (critical_count * 0.2) + (high_count * 0.1)
        
        return max(0.0, 1.0 - penalty)
    
    def _calculate_overall(
        self,
        scores: List[ConfidenceScore],
        risk_adjustment: float,
    ) -> float:
        if not scores:
            return self.fallback_confidence
        
        weighted_sum = sum(s.value * s.weight for s in scores)
        weight_sum = sum(s.weight for s in scores)
        
        if weight_sum == 0:
            return self.fallback_confidence
        
        overall = (weighted_sum / weight_sum) * risk_adjustment
        
        return min(1.0, max(0.0, overall))
