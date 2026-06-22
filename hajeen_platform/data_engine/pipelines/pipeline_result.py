"""Unified PipelineResult — نتيجة موحّدة لجميع تشغيلات الـ Pipeline.

يُستخدم هذا النوع كمخرج موحّد من أي pipeline بغض النظر عن طريقة التشغيل
(API trigger, CLI, Celery task, direct call).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class PipelineStatus(str, Enum):
    """حالة تشغيل الـ pipeline."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EMPTY = "empty"


@dataclass
class StageResult:
    """نتيجة مرحلة واحدة من الـ pipeline."""
    stage_name: str
    input_count: int
    output_count: int
    rejected_count: int
    duration_ms: float
    error_count: int
    errors: List[str] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        if self.input_count == 0:
            return 0.0
        return 1.0 - (self.output_count / self.input_count)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage_name,
            "input": self.input_count,
            "output": self.output_count,
            "rejected": self.rejected_count,
            "rejection_rate": round(self.rejection_rate, 4),
            "duration_ms": round(self.duration_ms, 2),
            "errors": self.error_count,
        }


@dataclass
class PipelineResult:
    """نتيجة موحّدة لتشغيل pipeline كامل.

    يحتوي على:
    - معلومات التشغيل (run_id, pipeline_name, source_id)
    - إحصائيات المقالات (input, output, stored)
    - مدة كل مرحلة
    - الأخطاء المسجّلة
    - الحالة النهائية
    """
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    pipeline_name: str = "pipeline"
    source_id: str = "unknown"
    status: PipelineStatus = PipelineStatus.SUCCESS

    input_count: int = 0
    output_count: int = 0
    stored_count: int = 0
    rejected_count: int = 0

    total_duration_ms: float = 0.0
    stage_results: List[StageResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    finished_at: Optional[datetime] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self) -> None:
        """تسجيل وقت الانتهاء وتحديد الحالة."""
        self.finished_at = datetime.now(tz=timezone.utc)
        if self.errors and self.output_count == 0:
            self.status = PipelineStatus.FAILED
        elif self.input_count == 0:
            self.status = PipelineStatus.EMPTY
        elif self.errors:
            self.status = PipelineStatus.PARTIAL
        else:
            self.status = PipelineStatus.SUCCESS

    @property
    def rejection_rate(self) -> float:
        if self.input_count == 0:
            return 0.0
        return 1.0 - (self.output_count / self.input_count)

    @property
    def success_rate(self) -> float:
        if self.input_count == 0:
            return 1.0
        return self.output_count / self.input_count

    def to_dict(self) -> Dict[str, Any]:
        """تحويل النتيجة إلى dict قابل للتسلسل."""
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "source_id": self.source_id,
            "status": self.status.value,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "stored_count": self.stored_count,
            "rejected_count": self.rejected_count,
            "rejection_rate": round(self.rejection_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "error_count": len(self.errors),
            "errors": self.errors[:10],  # أول 10 أخطاء فقط
            "stages": [s.to_dict() for s in self.stage_results],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_context(
        cls,
        context: Any,
        pipeline_name: str = "pipeline",
        stored_count: int = 0,
    ) -> "PipelineResult":
        """إنشاء PipelineResult من ProcessingContext."""
        from data_engine.processing.processing_context import ProcessingContext
        if not isinstance(context, ProcessingContext):
            raise TypeError(f"Expected ProcessingContext, got {type(context)}")

        result = cls(
            run_id=context.run_id,
            pipeline_name=pipeline_name,
            source_id=context.source_id,
            output_count=context.article_count,
            stored_count=stored_count,
            total_duration_ms=context.elapsed_ms,
            errors=[f"{e.stage}: {e.message}" for e in context.errors],
            metadata=dict(context.metadata),
        )
        result.stage_results = [
            StageResult(
                stage_name=t.stage_name,
                input_count=t.input_count,
                output_count=t.output_count,
                rejected_count=t.rejected_count,
                duration_ms=t.duration_ms,
                error_count=t.error_count,
            )
            for t in context.stage_traces
        ]
        # حساب input_count من trace أول مرحلة
        if result.stage_results:
            result.input_count = result.stage_results[0].input_count
            result.rejected_count = sum(s.rejected_count for s in result.stage_results)
        result.finish()
        return result
