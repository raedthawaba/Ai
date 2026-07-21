"""
Reflection Layer
================

Self-reflection on reasoning results for improvement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


@dataclass
class ReflectionInsight:
    category: str
    insight: str
    confidence: float
    actionable: bool = True


@dataclass
class ReflectionResult:
    insights: List[ReflectionInsight]
    improvement_suggestions: List[str]
    quality_assessment: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "insights": [
                {"category": i.category, "insight": i.insight, "confidence": i.confidence}
                for i in self.insights
            ],
            "improvement_suggestions": self.improvement_suggestions,
            "quality_assessment": self.quality_assessment,
            "metadata": self.metadata,
        }


class ReflectionLayer(BaseLayer):
    def __init__(self, config: Optional[LayerConfig] = None):
        super().__init__(config or LayerConfig(
            name="ReflectionLayer",
            layer_type=LayerType.REFLECTION,
        ))
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.REFLECTION
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            reasoning_steps = input_data.get("reasoning_steps", [])
            confidence = input_data.get("confidence", 0.0)
            
            insights = []
            suggestions = []
            
            if len(reasoning_steps) >= 3:
                insights.append(ReflectionInsight(
                    category="depth",
                    insight="Deep reasoning analysis",
                    confidence=0.9,
                ))
            else:
                suggestions.append("Consider adding more reasoning steps")
            
            if confidence < 0.5:
                insights.append(ReflectionInsight(
                    category="confidence",
                    insight="Low confidence, gather more info",
                    confidence=0.9,
                    actionable=True,
                ))
            
            quality = "good" if len(reasoning_steps) >= 2 and confidence >= 0.6 else "fair"
            
            result = ReflectionResult(
                insights=insights,
                improvement_suggestions=suggestions,
                quality_assessment=quality,
                metadata={"step_count": len(reasoning_steps)},
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
