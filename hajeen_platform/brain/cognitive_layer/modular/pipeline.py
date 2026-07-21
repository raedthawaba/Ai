"""
Reasoning Pipeline Layer
=======================

Orchestration layer that coordinates all other layers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from brain.cognitive_layer.modular.base import BaseLayer, LayerConfig, LayerResult, LayerType


class PipelinePhase(str, Enum):
    """Phases in the reasoning pipeline."""
    CONTEXT = "context"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    REFLECTION = "reflection"
    FINALIZATION = "finalization"


@dataclass
class PipelineStep:
    """Represents a step in the reasoning pipeline."""
    name: str
    phase: PipelinePhase
    layer_type: LayerType
    execute: Callable
    dependencies: List[str] = field(default_factory=list)
    optional: bool = False


@dataclass
class PipelineConfig:
    """Configuration for the reasoning pipeline."""
    enable_context: bool = True
    enable_strategy_selection: bool = True
    enable_verification: bool = True
    enable_reflection: bool = True
    enable_confidence: bool = True
    enable_explanation: bool = True
    stop_on_failure: bool = True


class ReasoningPipeline(BaseLayer):
    """
    Reasoning Pipeline Layer.
    
    Orchestrates the entire reasoning process by coordinating all other layers.
    """
    
    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        pipeline_config: Optional[PipelineConfig] = None,
    ):
        super().__init__(config or LayerConfig(
            name="ReasoningPipeline",
            layer_type=LayerType.PIPELINE,
        ))
        self.pipeline_config = pipeline_config or PipelineConfig()
        
        self._context_layer: Optional[Any] = None
        self._strategy_layer: Optional[Any] = None
        self._verification_layer: Optional[Any] = None
        self._reflection_layer: Optional[Any] = None
        self._confidence_engine: Optional[Any] = None
        self._explanation_engine: Optional[Any] = None
        
        self._steps: List[PipelineStep] = []
        self._build_default_steps()
    
    @property
    def layer_type(self) -> LayerType:
        return LayerType.PIPELINE
    
    def _build_default_steps(self) -> None:
        self._steps = [
            PipelineStep(
                name="build_context",
                phase=PipelinePhase.CONTEXT,
                layer_type=LayerType.CONTEXT,
                execute=lambda d: self._context_layer.execute(d) if self._context_layer else LayerResult(
                    layer_name="context", layer_type=LayerType.CONTEXT, success=True, data=d
                ),
            ),
            PipelineStep(
                name="select_strategy",
                phase=PipelinePhase.STRATEGY,
                layer_type=LayerType.STRATEGY_SELECTOR,
                dependencies=["build_context"],
                execute=lambda d: self._strategy_layer.execute(d) if self._strategy_layer else LayerResult(
                    layer_name="strategy", layer_type=LayerType.STRATEGY_SELECTOR, success=True, data=d
                ),
            ),
            PipelineStep(
                name="execute_reasoning",
                phase=PipelinePhase.EXECUTION,
                layer_type=LayerType.PIPELINE,
                dependencies=["select_strategy"],
                execute=lambda d: LayerResult(
                    layer_name="execution", layer_type=LayerType.PIPELINE, success=True, data=d
                ),
            ),
            PipelineStep(
                name="verify_result",
                phase=PipelinePhase.VERIFICATION,
                layer_type=LayerType.VERIFICATION,
                dependencies=["execute_reasoning"],
                optional=True,
                execute=lambda d: self._verification_layer.execute(d) if self._verification_layer else LayerResult(
                    layer_name="verification", layer_type=LayerType.VERIFICATION, success=True, data=d
                ),
            ),
            PipelineStep(
                name="reflect",
                phase=PipelinePhase.REFLECTION,
                layer_type=LayerType.REFLECTION,
                dependencies=["verify_result"],
                optional=True,
                execute=lambda d: self._reflection_layer.execute(d) if self._reflection_layer else LayerResult(
                    layer_name="reflection", layer_type=LayerType.REFLECTION, success=True, data=d
                ),
            ),
        ]
    
    def inject_layer(self, layer_type: LayerType, layer: Any) -> None:
        if layer_type == LayerType.CONTEXT:
            self._context_layer = layer
        elif layer_type == LayerType.STRATEGY_SELECTOR:
            self._strategy_layer = layer
        elif layer_type == LayerType.VERIFICATION:
            self._verification_layer = layer
        elif layer_type == LayerType.REFLECTION:
            self._reflection_layer = layer
        elif layer_type == LayerType.CONFIDENCE:
            self._confidence_engine = layer
        elif layer_type == LayerType.EXPLANATION:
            self._explanation_engine = layer
    
    async def initialize(self) -> None:
        self._initialized = True
    
    async def execute(self, input_data: Dict[str, Any]) -> LayerResult:
        start_time = time.perf_counter()
        
        try:
            reasoning_id = input_data.get("reasoning_id", "unknown")
            
            phase_results: Dict[PipelinePhase, LayerResult] = {}
            accumulated_data = dict(input_data)
            errors = []
            warnings = []
            
            for step in self._steps:
                if not self._is_step_enabled(step.phase):
                    continue
                
                try:
                    result = await step.execute(accumulated_data)
                    
                    if result.success:
                        phase_results[step.phase] = result
                        accumulated_data.update(result.data)
                        warnings.extend(result.warnings)
                    else:
                        errors.append(f"{step.name}: {result.error}")
                        if self.pipeline_config.stop_on_failure:
                            break
                            
                except Exception as e:
                    errors.append(f"{step.name}: {str(e)}")
                    if self.pipeline_config.stop_on_failure:
                        break
            
            total_time = (time.perf_counter() - start_time) * 1000
            
            return LayerResult(
                layer_name=self.name,
                layer_type=self.layer_type,
                success=len(errors) == 0,
                data={
                    "reasoning_id": reasoning_id,
                    "phase_results": {phase.value: r.to_dict() for phase, r in phase_results.items()},
                    "errors": errors,
                    "total_time_ms": total_time,
                },
                error="; ".join(errors) if errors else None,
                warnings=warnings,
                execution_time_ms=total_time,
            )
            
        except Exception as e:
            return LayerResult(
                layer_name=self.name,
                layer_type=self.layer_type,
                success=False,
                error=str(e),
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )
    
    def _is_step_enabled(self, phase: PipelinePhase) -> bool:
        if not self.pipeline_config.enable_context and phase == PipelinePhase.CONTEXT:
            return False
        if not self.pipeline_config.enable_strategy_selection and phase == PipelinePhase.STRATEGY:
            return False
        if not self.pipeline_config.enable_verification and phase == PipelinePhase.VERIFICATION:
            return False
        if not self.pipeline_config.enable_reflection and phase == PipelinePhase.REFLECTION:
            return False
        return True
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phases": [s.phase.value for s in self._steps],
            "steps": [
                {"name": s.name, "phase": s.phase.value, "optional": s.optional}
                for s in self._steps
            ],
        }
