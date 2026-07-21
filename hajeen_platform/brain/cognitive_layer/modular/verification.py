"""
Verification Layer
=================

Verifies reasoning results for correctness and quality.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


class VerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class VerificationCheck:
    rule_name: str
    status: VerificationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    overall_status: VerificationStatus
    checks: List[VerificationCheck]
    score: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "score": self.score,
            "checks": [
                {"rule_name": c.rule_name, "status": c.status.value, "message": c.message}
                for c in self.checks
            ],
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


class VerificationLayer(BaseLayer):
    def __init__(self, config: Optional[LayerConfig] = None):
        super().__init__(config or LayerConfig(
            name="VerificationLayer",
            layer_type=LayerType.VERIFICATION,
        ))
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.VERIFICATION
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            reasoning_steps = input_data.get("reasoning_steps", [])
            confidence = input_data.get("confidence", 0.5)
            
            checks = []
            
            if len(reasoning_steps) >= 1:
                checks.append(VerificationCheck(
                    rule_name="minimum_steps",
                    status=VerificationStatus.PASSED,
                    message=f"Has {len(reasoning_steps)} reasoning steps",
                ))
            else:
                checks.append(VerificationCheck(
                    rule_name="minimum_steps",
                    status=VerificationStatus.WARNING,
                    message="No reasoning steps found",
                ))
            
            if 0 <= confidence <= 1:
                checks.append(VerificationCheck(
                    rule_name="valid_confidence",
                    status=VerificationStatus.PASSED,
                    message=f"Valid confidence: {confidence:.2f}",
                ))
            else:
                checks.append(VerificationCheck(
                    rule_name="valid_confidence",
                    status=VerificationStatus.FAILED,
                    message=f"Invalid confidence: {confidence}",
                ))
            
            failed = [c for c in checks if c.status == VerificationStatus.FAILED]
            overall = VerificationStatus.FAILED if failed else VerificationStatus.PASSED
            score = sum(1 for c in checks if c.status == VerificationStatus.PASSED) / max(1, len(checks))
            
            result = VerificationResult(
                overall_status=overall,
                checks=checks,
                score=score,
                recommendations=[c.message for c in failed],
                metadata={"rule_count": len(checks)},
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
