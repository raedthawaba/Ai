"""Planning Engine Pipeline - Orchestration System."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PipelineState(str, Enum):
    """حالات الـ Pipeline."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageType(str, Enum):
    """أنواع المراحل."""
    VALIDATION = "validation"
    TRANSFORMATION = "transformation"
    PROCESSING = "processing"
    AGGREGATION = "aggregation"
    OUTPUT = "output"


@dataclass
class StageResult:
    """نتيجة مرحلة واحدة."""
    stage_id: str
    stage_name: str
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass 
class PipelineStage:
    """مرحلة واحدة في الـ Pipeline."""
    stage_id: str
    name: str
    stage_type: StageType
    handler: Callable[[Any], Any]
    condition: Optional[Callable[[Any], bool]] = None
    timeout_seconds: float = 60.0
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.stage_id is None:
            self.stage_id = str(uuid.uuid4())


@dataclass
class PipelineContext:
    """سياق الـ Pipeline."""
    pipeline_id: str
    plan_id: Optional[str] = None
    correlation_id: Optional[str] = None
    input_data: Any = None
    shared_data: Dict[str, Any] = field(default_factory=dict)
    results: List[StageResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)

    def get_result(self, stage_name: str) -> Optional[Any]:
        """الحصول على نتيجة مرحلة معينة."""
        for result in self.results:
            if result.stage_name == stage_name:
                return result.data
        return None

    def has_error(self) -> bool:
        """التحقق من وجود أخطاء."""
        return any(not r.success for r in self.results)


class PipelineOrchestrator:
    """
    مُنسق Pipeline للتنفيذ المتسلسل والمرحلي.
    
    الميزات:
    - تنفيذ مرحلي مع تبعيات
    - دعم التنفيذ المتوازي
    - معالجة الأخطاء والتكرار
    - توقيت المراحل
    - تتبع السياق
    """

    def __init__(self, name: str = "default") -> None:
        self._name = name
        self._stages: List[PipelineStage] = []
        self._running_pipelines: Dict[str, PipelineContext] = {}
        self._completed_pipelines: List[PipelineContext] = []
        self._max_completed = 100
        self._lock = asyncio.Lock()

    def add_stage(self, stage: PipelineStage) -> str:
        """إضافة مرحلة للـ Pipeline."""
        stage.stage_id = stage.stage_id or str(uuid.uuid4())
        self._stages.append(stage)
        logger.info(
            "pipeline[%s]: added stage=%s type=%s",
            self._name, stage.name, stage.stage_type.value
        )
        return stage.stage_id

    def create_stage(
        self,
        name: str,
        stage_type: StageType,
        handler: Callable[[Any], Any],
        condition: Optional[Callable[[Any], bool]] = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ) -> PipelineStage:
        """إنشاء وإضافة مرحلة."""
        stage = PipelineStage(
            stage_id=str(uuid.uuid4()),
            name=name,
            stage_type=stage_type,
            handler=handler,
            condition=condition,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            metadata=kwargs,
        )
        self.add_stage(stage)
        return stage

    def remove_stage(self, stage_id: str) -> bool:
        """إزالة مرحلة."""
        for i, stage in enumerate(self._stages):
            if stage.stage_id == stage_id:
                del self._stages[i]
                logger.info("pipeline[%s]: removed stage=%s", self._name, stage.name)
                return True
        return False

    async def execute(
        self,
        input_data: Any,
        plan_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> PipelineContext:
        """تنفيذ الـ Pipeline."""
        pipeline_id = str(uuid.uuid4())
        
        context = PipelineContext(
            pipeline_id=pipeline_id,
            plan_id=plan_id,
            correlation_id=correlation_id,
            input_data=input_data,
        )
        
        self._running_pipelines[pipeline_id] = context
        
        try:
            current_data = input_data
            
            for stage in self._stages:
                if not stage.enabled:
                    continue
                
                # التحقق من الشرط
                if stage.condition and not stage.condition(current_data):
                    logger.info(
                        "pipeline[%s]: skipping stage=%s (condition not met)",
                        self._name, stage.name
                    )
                    continue
                
                result = await self._execute_stage(stage, current_data, context)
                context.results.append(result)
                
                if result.success:
                    current_data = result.data
                else:
                    # التكرار عند الفشل
                    if stage.retry_count < stage.max_retries:
                        stage.retry_count += 1
                        logger.warning(
                            "pipeline[%s]: retrying stage=%s attempt=%d",
                            self._name, stage.name, stage.retry_count
                        )
                        retry_result = await self._execute_stage(stage, current_data, context)
                        context.results[-1] = retry_result
                        if retry_result.success:
                            current_data = retry_result.data
                            stage.retry_count = 0
                            continue
                    
                    logger.error(
                        "pipeline[%s]: stage failed=%s error=%s",
                        self._name, stage.name, result.error
                    )
                    break
            
            context.shared_data["output"] = current_data
            
        except Exception as e:
            logger.exception("pipeline[%s]: execution failed", self._name)
            context.metadata["error"] = str(e)
        
        finally:
            async with self._lock:
                self._running_pipelines.pop(pipeline_id, None)
                self._completed_pipelines.append(context)
                if len(self._completed_pipelines) > self._max_completed:
                    self._completed_pipelines.pop(0)
        
        return context

    async def _execute_stage(
        self,
        stage: PipelineStage,
        input_data: Any,
        context: PipelineContext,
    ) -> StageResult:
        """تنفيذ مرحلة واحدة."""
        started_at = datetime.utcnow()
        
        try:
            if asyncio.iscoroutinefunction(stage.handler):
                data = await asyncio.wait_for(
                    stage.handler(input_data, context),
                    timeout=stage.timeout_seconds
                )
            else:
                loop = asyncio.get_event_loop()
                data = await asyncio.wait_for(
                    loop.run_in_executor(lambda: stage.handler(input_data, context)),
                    timeout=stage.timeout_seconds
                )
            
            completed_at = datetime.utcnow()
            duration_ms = (completed_at - started_at).total_seconds() * 1000
            
            return StageResult(
                stage_id=stage.stage_id,
                stage_name=stage.name,
                success=True,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                data=data,
            )
            
        except asyncio.TimeoutError:
            completed_at = datetime.utcnow()
            duration_ms = (completed_at - started_at).total_seconds() * 1000
            
            return StageResult(
                stage_id=stage.stage_id,
                stage_name=stage.name,
                success=False,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                error=f"Timeout after {stage.timeout_seconds}s",
            )
            
        except Exception as e:
            completed_at = datetime.utcnow()
            duration_ms = (completed_at - started_at).total_seconds() * 1000
            
            return StageResult(
                stage_id=stage.stage_id,
                stage_name=stage.name,
                success=False,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                error=str(e),
            )

    async def execute_parallel(
        self,
        input_data: Any,
        plan_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> PipelineContext:
        """تنفيذ الـ Pipeline مع مراحل متوازية."""
        pipeline_id = str(uuid.uuid4())
        
        context = PipelineContext(
            pipeline_id=pipeline_id,
            plan_id=plan_id,
            correlation_id=correlation_id,
            input_data=input_data,
        )
        
        self._running_pipelines[pipeline_id] = context
        
        try:
            current_data = input_data
            stage_groups: List[List[PipelineStage]] = []
            current_group: List[PipelineStage] = []
            
            # تجميع المراحل المتوازية
            for stage in self._stages:
                if not stage.enabled:
                    continue
                    
                if stage.stage_type == StageType.PROCESSING and current_group:
                    stage_groups.append(current_group)
                    current_group = []
                
                current_group.append(stage)
            
            if current_group:
                stage_groups.append(current_group)
            
            # تنفيذ كل مجموعة
            for group_idx, group in enumerate(stage_groups):
                if len(group) == 1:
                    # تنفيذ فردي
                    stage = group[0]
                    if stage.condition and not stage.condition(current_data):
                        continue
                    result = await self._execute_stage(stage, current_data, context)
                    context.results.append(result)
                    if result.success:
                        current_data = result.data
                    else:
                        break
                else:
                    # تنفيذ متوازي
                    tasks = []
                    for stage in group:
                        if stage.condition and not stage.condition(current_data):
                            continue
                        tasks.append(self._execute_stage(stage, current_data, context))
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for stage, result in zip(group, results):
                        if isinstance(result, Exception):
                            result = StageResult(
                                stage_id=stage.stage_id,
                                stage_name=stage.name,
                                success=False,
                                started_at=datetime.utcnow(),
                                error=str(result),
                            )
                        context.results.append(result)
                        
                        if result.success:
                            current_data = result.data
            
            context.shared_data["output"] = current_data
            
        except Exception as e:
            logger.exception("pipeline[%s]: parallel execution failed", self._name)
            context.metadata["error"] = str(e)
        
        finally:
            async with self._lock:
                self._running_pipelines.pop(pipeline_id, None)
                self._completed_pipelines.append(context)
        
        return context

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineContext]:
        """الحصول على سياق خط أنابيب."""
        return self._running_pipelines.get(pipeline_id)

    def get_running_pipelines(self) -> List[PipelineContext]:
        """الحصول على خطوط الأنابيب الجارية."""
        return list(self._running_pipelines.values())

    def get_completed_pipelines(self, limit: int = 10) -> List[PipelineContext]:
        """الحصول على خطوط الأنابيب المكتملة."""
        return self._completed_pipelines[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات."""
        total = len(self._completed_pipelines)
        successful = sum(1 for p in self._completed_pipelines if not p.has_error())
        
        return {
            "name": self._name,
            "stages_count": len(self._stages),
            "running_count": len(self._running_pipelines),
            "completed_count": total,
            "success_rate": successful / total if total > 0 else 0,
            "stages": [
                {
                    "name": s.name,
                    "type": s.stage_type.value,
                    "enabled": s.enabled,
                }
                for s in self._stages
            ],
        }


# Factory for creating pipelines
class PipelineFactory:
    """مصنع لإنشاء خطوط أنابيب معدة مسبقاً."""

    @staticmethod
    def create_validation_pipeline() -> PipelineOrchestrator:
        """إنشاء خط أنابيب للتحقق."""
        pipeline = PipelineOrchestrator("validation")
        
        pipeline.create_stage(
            name="input_check",
            stage_type=StageType.VALIDATION,
            handler=lambda data, ctx: {"valid": data is not None, "data": data},
        )
        
        pipeline.create_stage(
            name="schema_validation",
            stage_type=StageType.VALIDATION,
            handler=lambda data, ctx: data,
        )
        
        return pipeline

    @staticmethod
    def create_processing_pipeline() -> PipelineOrchestrator:
        """إنشاء خط أنابيب للمعالجة."""
        pipeline = PipelineOrchestrator("processing")
        
        pipeline.create_stage(
            name="transform",
            stage_type=StageType.TRANSFORMATION,
            handler=lambda data, ctx: data,
        )
        
        pipeline.create_stage(
            name="process",
            stage_type=StageType.PROCESSING,
            handler=lambda data, ctx: data,
        )
        
        pipeline.create_stage(
            name="aggregate",
            stage_type=StageType.AGGREGATION,
            handler=lambda data, ctx: data,
        )
        
        pipeline.create_stage(
            name="output",
            stage_type=StageType.OUTPUT,
            handler=lambda data, ctx: data,
        )
        
        return pipeline
