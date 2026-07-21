"""Planning Engine - Execution Trace System."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class TraceEventType(str, Enum):
    """أنواع أحداث التتبع."""
    PLAN_CREATED = "plan_created"
    PLAN_STARTED = "plan_started"
    PLAN_COMPLETED = "plan_completed"
    PLAN_FAILED = "plan_failed"
    PLAN_CANCELLED = "plan_cancelled"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_RETRY = "step_retry"
    ENGINE_STARTED = "engine_started"
    ENGINE_STOPPED = "engine_stopped"
    METRICS_COLLECTED = "metrics_collected"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"


class TraceLevel(str, Enum):
    """مستويات التتبع."""
    MINIMAL = "minimal"
    STANDARD = "standard"
    VERBOSE = "verbose"


@dataclass
class TraceEvent:
    """حدث تتبع واحد."""
    event_id: str
    trace_id: str
    event_type: TraceEventType
    timestamp: float
    step_number: Optional[int] = None
    duration_ms: Optional[float] = None
    success: bool = True
    
    # الهوية
    plan_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    stage_name: Optional[str] = None
    
    # البيانات
    event_name: str = ""
    description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # الأخطاء
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "step_number": self.step_number,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "plan_id": self.plan_id,
            "pipeline_id": self.pipeline_id,
            "stage_name": self.stage_name,
            "event_name": self.event_name,
            "description": self.description,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "metadata": self.metadata,
            "error_message": self.error_message,
            "error_type": self.error_type,
        }


@dataclass
class ExecutionTrace:
    """سجل تنفيذ كامل."""
    trace_id: str
    plan_id: str
    created_at: float
    completed_at: Optional[float] = None
    
    # المعلومات
    plan_name: str = ""
    plan_description: str = ""
    
    # الأحداث
    events: List[TraceEvent] = field(default_factory=list)
    
    # الإحصائيات
    total_duration_ms: Optional[float] = None
    step_count: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    retry_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    # الحالة
    success: bool = True
    final_result: Optional[Any] = None
    
    # مستوى التتبع
    level: TraceLevel = TraceLevel.STANDARD

    def add_event(self, event: TraceEvent) -> None:
        """إضافة حدث للتتبع."""
        self.events.append(event)
        
        # تحديث الإحصائيات
        if event.event_type == TraceEventType.STEP_COMPLETED:
            self.completed_steps += 1
        elif event.event_type == TraceEventType.STEP_FAILED:
            self.failed_steps += 1
        elif event.event_type == TraceEventType.STEP_RETRY:
            self.retry_count += 1
        elif event.event_type == TraceEventType.CACHE_HIT:
            self.cache_hits += 1
        elif event.event_type == TraceEventType.CACHE_MISS:
            self.cache_misses += 1

    def complete(self, success: bool = True, result: Any = None) -> None:
        """إكمال التتبع."""
        self.completed_at = time.time()
        self.total_duration_ms = (self.completed_at - self.created_at) * 1000
        self.success = success
        self.final_result = result

    def get_duration_summary(self) -> Dict[str, Any]:
        """ملخص المدة."""
        if not self.total_duration_ms:
            self.total_duration_ms = (time.time() - self.created_at) * 1000
        
        return {
            "total_ms": self.total_duration_ms,
            "total_seconds": self.total_duration_ms / 1000,
            "step_count": self.step_count,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "retry_count": self.retry_count,
            "success_rate": (
                self.completed_steps / self.step_count 
                if self.step_count > 0 else 1.0
            ),
        }

    def get_error_summary(self) -> List[Dict[str, Any]]:
        """ملخص الأخطاء."""
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "timestamp": e.timestamp,
                "stage_name": e.stage_name,
            }
            for e in self.events
            if not e.success and e.error_message
        ]

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس."""
        result = {
            "trace_id": self.trace_id,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "created_at_iso": datetime.fromtimestamp(self.created_at).isoformat(),
            "completed_at": self.completed_at,
            "plan_name": self.plan_name,
            "plan_description": self.plan_description,
            "events_count": len(self.events),
            "total_duration_ms": self.total_duration_ms,
            "step_count": self.step_count,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "retry_count": self.retry_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "success": self.success,
            "level": self.level.value,
        }
        
        if self.level == TraceLevel.VERBOSE:
            result["events"] = [e.to_dict() for e in self.events]
        
        return result

    def save_to_file(self, path: Path) -> None:
        """حفظ التتبع إلى ملف."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("trace_saved", trace_id=self.trace_id, path=str(path))


class ExecutionTraceManager:
    """
    مدير سجلات التنفيذ.
    
    الميزات:
    - تسجيل الأحداث في الوقت الفعلي
    - تخزين التتبعات المكتملة
    - البحث والتصفية
    - تصدير التتبعات
    - إحصائيات التنفيذ
    """

    def __init__(
        self,
        enabled: bool = True,
        level: TraceLevel = TraceLevel.STANDARD,
        storage_path: Optional[Path] = None,
        persist_traces: bool = False,
        max_traces: int = 1000,
    ) -> None:
        self.enabled = enabled
        self.level = level
        self.storage_path = storage_path
        self.persist_traces = persist_traces
        self.max_traces = max_traces
        
        self._active_traces: Dict[str, ExecutionTrace] = {}
        self._completed_traces: List[ExecutionTrace] = []
        self._lock = asyncio.Lock()

    async def start_trace(
        self,
        plan_id: str,
        plan_name: str = "",
        plan_description: str = "",
        level: Optional[TraceLevel] = None,
    ) -> ExecutionTrace:
        """بدء تتبع جديد."""
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4()),
            plan_id=plan_id,
            created_at=time.time(),
            plan_name=plan_name,
            plan_description=plan_description,
            level=level or self.level,
        )
        
        async with self._lock:
            self._active_traces[plan_id] = trace
        
        self._record_event(
            trace,
            TraceEventType.PLAN_CREATED,
            "plan_created",
            f"Plan {plan_name} created",
        )
        
        logger.info("trace: started plan_id=%s trace_id=%s", plan_id, trace.trace_id)
        return trace

    async def end_trace(
        self,
        plan_id: str,
        success: bool = True,
        result: Any = None,
    ) -> Optional[ExecutionTrace]:
        """إنهاء تتبع."""
        async with self._lock:
            trace = self._active_traces.pop(plan_id, None)
        
        if not trace:
            return None
        
        event_type = (
            TraceEventType.PLAN_COMPLETED if success else TraceEventType.PLAN_FAILED
        )
        
        trace.complete(success, result)
        
        self._record_event(
            trace,
            event_type,
            "plan_ended",
            f"Plan ended with success={success}",
            success=success,
        )
        
        async with self._lock:
            self._completed_traces.append(trace)
            if len(self._completed_traces) > self.max_traces:
                self._completed_traces.pop(0)
        
        if self.persist_traces and self.storage_path:
            filename = f"trace_{trace.trace_id}.json"
            trace.save_to_file(self.storage_path / filename)
        
        logger.info(
            "trace: ended plan_id=%s trace_id=%s duration_ms=%.2f success=%s",
            plan_id, trace.trace_id, trace.total_duration_ms or 0, success
        )
        
        return trace

    def record_step_start(
        self,
        plan_id: str,
        step_name: str,
        step_number: int,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """تسجيل بدء خطوة."""
        trace = self._active_traces.get(plan_id)
        if not trace or not self.enabled:
            return
        
        trace.step_count += 1
        
        self._record_event(
            trace,
            TraceEventType.STEP_STARTED,
            step_name,
            f"Step {step_number} started",
            step_number=step_number,
            input_data=input_data or {},
        )

    def record_step_complete(
        self,
        plan_id: str,
        step_name: str,
        step_number: int,
        output_data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """تسجيل إكمال خطوة."""
        trace = self._active_traces.get(plan_id)
        if not trace or not self.enabled:
            return
        
        self._record_event(
            trace,
            TraceEventType.STEP_COMPLETED,
            step_name,
            f"Step {step_number} completed",
            step_number=step_number,
            duration_ms=duration_ms,
            output_data=output_data or {},
            success=True,
        )

    def record_step_failed(
        self,
        plan_id: str,
        step_name: str,
        step_number: int,
        error: Exception,
        duration_ms: Optional[float] = None,
    ) -> None:
        """تسجيل فشل خطوة."""
        trace = self._active_traces.get(plan_id)
        if not trace or not self.enabled:
            return
        
        self._record_event(
            trace,
            TraceEventType.STEP_FAILED,
            step_name,
            f"Step {step_number} failed",
            step_number=step_number,
            duration_ms=duration_ms,
            success=False,
            error_message=str(error),
            error_type=type(error).__name__,
        )

    def record_retry(
        self,
        plan_id: str,
        step_name: str,
        step_number: int,
        attempt: int,
        max_attempts: int,
    ) -> None:
        """تسجيل إعادة محاولة."""
        trace = self._active_traces.get(plan_id)
        if not trace or not self.enabled:
            return
        
        self._record_event(
            trace,
            TraceEventType.STEP_RETRY,
            step_name,
            f"Retry {attempt}/{max_attempts}",
            step_number=step_number,
            metadata={"attempt": attempt, "max_attempts": max_attempts},
        )

    def record_cache_access(
        self,
        plan_id: str,
        cache_key: str,
        hit: bool,
    ) -> None:
        """تسجيل وصول للـ cache."""
        trace = self._active_traces.get(plan_id)
        if not trace or not self.enabled:
            return
        
        event_type = TraceEventType.CACHE_HIT if hit else TraceEventType.CACHE_MISS
        
        self._record_event(
            trace,
            event_type,
            "cache_access",
            f"Cache {'hit' if hit else 'miss'}: {cache_key[:50]}",
            metadata={"cache_key": cache_key, "hit": hit},
        )

    def _record_event(
        self,
        trace: ExecutionTrace,
        event_type: TraceEventType,
        event_name: str,
        description: str,
        success: bool = True,
        step_number: Optional[int] = None,
        duration_ms: Optional[float] = None,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """تسجيل حدث داخلياً."""
        if self.level == TraceLevel.MINIMAL and event_type not in [
            TraceEventType.PLAN_CREATED,
            TraceEventType.PLAN_COMPLETED,
            TraceEventType.PLAN_FAILED,
        ]:
            return
        
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace.trace_id,
            event_type=event_type,
            timestamp=time.time(),
            step_number=step_number,
            duration_ms=duration_ms,
            success=success,
            plan_id=trace.plan_id,
            event_name=event_name,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {},
            metadata=metadata or {},
            error_message=error_message,
            error_type=error_type,
        )
        
        trace.add_event(event)

    def get_trace(self, plan_id: str) -> Optional[ExecutionTrace]:
        """الحصول على تتبع معين."""
        return self._active_traces.get(plan_id)

    def get_completed_traces(self, limit: int = 10) -> List[ExecutionTrace]:
        """الحصول على التتبعات المكتملة."""
        return self._completed_traces[-limit:]

    def search_traces(
        self,
        plan_name: Optional[str] = None,
        success: Optional[bool] = None,
        min_duration_ms: Optional[float] = None,
        limit: int = 100,
    ) -> List[ExecutionTrace]:
        """البحث في التتبعات."""
        traces = list(self._completed_traces)
        
        if plan_name:
            traces = [t for t in traces if plan_name.lower() in t.plan_name.lower()]
        
        if success is not None:
            traces = [t for t in traces if t.success == success]
        
        if min_duration_ms is not None:
            traces = [
                t for t in traces 
                if t.total_duration_ms and t.total_duration_ms >= min_duration_ms
            ]
        
        return traces[:limit]

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات التتبع."""
        total = len(self._completed_traces)
        successful = [t for t in self._completed_traces if t.success]
        
        all_durations = [
            t.total_duration_ms for t in self._completed_traces 
            if t.total_duration_ms
        ]
        
        return {
            "total_traces": total,
            "active_traces": len(self._active_traces),
            "successful_traces": len(successful),
            "failed_traces": total - len(successful),
            "success_rate": len(successful) / total if total > 0 else 0,
            "avg_duration_ms": sum(all_durations) / len(all_durations) if all_durations else 0,
            "total_cache_hits": sum(t.cache_hits for t in self._completed_traces),
            "total_cache_misses": sum(t.cache_misses for t in self._completed_traces),
            "total_retries": sum(t.retry_count for t in self._completed_traces),
        }

    async def clear_completed(self) -> int:
        """مسح التتبعات المكتملة."""
        count = len(self._completed_traces)
        async with self._lock:
            self._completed_traces.clear()
        logger.info("trace: cleared %d completed traces", count)
        return count


# Singleton instance
_trace_manager: Optional[ExecutionTraceManager] = None


def get_trace_manager() -> ExecutionTraceManager:
    """الحصول على مدير التتبع الوحيد."""
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = ExecutionTraceManager()
    return _trace_manager
