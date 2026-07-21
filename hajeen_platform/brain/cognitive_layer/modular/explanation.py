"""
Explanation Engine Layer
======================

Generates human-readable explanations for reasoning results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


@dataclass
class ExplanationSection:
    """A section of the explanation."""
    title: str
    content: str
    importance: int = 1


@dataclass
class ExplanationResult:
    """Result of explanation generation."""
    summary: str
    sections: List[ExplanationSection]
    reasoning_chain: List[str]
    confidence_factors: List[str]
    limitations: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "sections": [
                {"title": s.title, "content": s.content, "importance": s.importance}
                for s in self.sections
            ],
            "reasoning_chain": self.reasoning_chain,
            "confidence_factors": self.confidence_factors,
            "limitations": self.limitations,
            "metadata": self.metadata,
        }


class ExplanationEngine(BaseLayer):
    """Explanation Engine Layer."""
    
    def __init__(self, config: Optional[LayerConfig] = None, language: str = "ar"):
        super().__init__(config or LayerConfig(
            name="ExplanationEngine",
            layer_type=LayerType.EXPLANATION,
        ))
        self.language = language
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.EXPLANATION
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            problem = input_data.get("problem", "")
            strategy = input_data.get("strategy", "unknown")
            reasoning_steps = input_data.get("reasoning_steps", [])
            solutions = input_data.get("solutions", [])
            risks = input_data.get("risks", [])
            confidence = input_data.get("confidence", 0.0)
            
            summary = self._build_summary(problem, strategy)
            sections = self._build_sections(reasoning_steps, solutions, risks)
            reasoning_chain = self._build_reasoning_chain(reasoning_steps)
            confidence_factors = [f"Confidence: {confidence:.2%}"]
            limitations = self._build_limitations(reasoning_steps, risks)
            
            result = ExplanationResult(
                summary=summary,
                sections=sections,
                reasoning_chain=reasoning_chain,
                confidence_factors=confidence_factors,
                limitations=limitations,
                metadata={"language": self.language},
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
    
    def _build_summary(self, problem: str, strategy: str) -> str:
        return f"Analysis of: {problem[:100]}{'...' if len(problem) > 100 else ''}"
    
    def _build_sections(self, steps, solutions, risks) -> List[ExplanationSection]:
        sections = []
        if steps:
            sections.append(ExplanationSection(
                title="Steps" if self.language == "en" else "الخطوات",
                content=f"{len(steps)} steps completed",
                importance=5,
            ))
        return sections
    
    def _build_reasoning_chain(self, steps) -> List[str]:
        return [f"Step {i+1}: {s.get('description', '')}" for i, s in enumerate(steps)]
    
    def _build_limitations(self, steps, risks) -> List[str]:
        return ["Analysis complete" if steps else "Limited reasoning steps"]
