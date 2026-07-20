"""
Execution Trace — سجل التنفيذ التفصيلي
=======================================

يسجل كل خطوة في عملية الاستدلال بشكل تفصيلي.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class TraceEventType(str, Enum):
    """أنواع أحداث التتبع."""
    ENGINE_START = "engine_start"
    ENGINE_COMPLETE = "engine_complete"
    ENGINE_ERROR = "engine_error"
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    STEP_ERROR = "step_error"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_COMPLETE = "llm_call_complete"
    LLM_CALL_ERROR = "llm_call_error"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    FALLBACK_TRIGGERED = "fallback_triggered"
    RETRY_ATTEMPT = "retry_attempt"
    VALIDATION = "validation"


class TraceLevel(str, Enum):
    """مستويات التتبع."""
    MINIMAL = "minimal"      # فقط الأحداث الرئيسية
    STANDARD = "standard"    # الأحداث والنتائج
    VERBOSE = "verbose"      # كل شيء مفصل


@dataclass
class TraceEvent:
    """حدث واحد في التتبع."""
    event_id: str
    trace_id: str
    event_type: TraceEventType
    timestamp: float
    step_number: Optional[int]
    duration_ms: Optional[float]
    success: bool
    
    # البيانات
    event_name: str
    description: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # الأخطاء
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
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
    """سجل تنفيذ كامل لعملية استدلال."""
    trace_id: str
    reasoning_id: str
    created_at: float
    completed_at: Optional[float] = None
    
    # المعلومات الأساسية
    problem: str = ""
    strategy: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    
    # الأحداث
    events: List[TraceEvent] = field(default_factory=list)
    
    # الإحصائيات
    total_duration_ms: Optional[float] = None
    llm_calls_count: int = 0
    retries_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    fallback_triggered: bool = False
    
    # الحالة النهائية
    success: bool = True
    final_confidence: float = 0.0
    
    # مستوى التتبع
    level: TraceLevel = TraceLevel.STANDARD
    
    def add_event(self, event: TraceEvent) -> None:
        """إضافة حدث للتتبع."""
        self.events.append(event)
        
        # تحديث الإحصائيات
        if event.event_type == TraceEventType.LLM_CALL_COMPLETE:
            self.llm_calls_count += 1
        elif event.event_type == TraceEventType.CACHE_HIT:
            self.cache_hits += 1
        elif event.event_type == TraceEventType.CACHE_MISS:
            self.cache_misses += 1
        elif event.event_type == TraceEventType.RETRY_ATTEMPT:
            self.retries_count += 1
        elif event.event_type == TraceEventType.FALLBACK_TRIGGERED:
            self.fallback_triggered = True
    
    def complete(self, success: bool = True, final_confidence: float = 0.0) -> None:
        """إكمال التتبع."""
        self.completed_at = time.time()
        self.total_duration_ms = (self.completed_at - self.created_at) * 1000
        self.success = success
        self.final_confidence = final_confidence
    
    def get_duration_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص المدة."""
        if not self.total_duration_ms:
            self.total_duration_ms = (time.time() - self.created_at) * 1000
        
        return {
            "total_ms": self.total_duration_ms,
            "total_seconds": self.total_duration_ms / 1000,
            "llm_calls": self.llm_calls_count,
            "avg_llm_time_ms": (
                sum(e.duration_ms or 0 for e in self.events 
                    if e.event_type == TraceEventType.LLM_CALL_COMPLETE) 
                / max(self.llm_calls_count, 1)
            ),
        }
    
    def get_error_summary(self) -> List[Dict[str, Any]]:
        """الحصول على ملخص الأخطاء."""
        errors = []
        for event in self.events:
            if event.event_type in (
                TraceEventType.ENGINE_ERROR,
                TraceEventType.STEP_ERROR,
                TraceEventType.LLM_CALL_ERROR,
            ):
                errors.append({
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "error_type": event.error_type,
                    "error_message": event.error_message,
                    "timestamp": event.timestamp,
                    "step_number": event.step_number,
                })
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس."""
        return {
            "trace_id": self.trace_id,
            "reasoning_id": self.reasoning_id,
            "created_at": self.created_at,
            "created_at_iso": datetime.fromtimestamp(self.created_at).isoformat(),
            "completed_at": self.completed_at,
            "completed_at_iso": (
                datetime.fromtimestamp(self.completed_at).isoformat() 
                if self.completed_at else None
            ),
            "problem": self.problem,
            "strategy": self.strategy,
            "context_keys": list(self.context.keys()),
            "events_count": len(self.events),
            "total_duration_ms": self.total_duration_ms,
            "llm_calls_count": self.llm_calls_count,
            "retries_count": self.retries_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "fallback_triggered": self.fallback_triggered,
            "success": self.success,
            "final_confidence": self.final_confidence,
            "level": self.level.value,
            "events": [e.to_dict() for e in self.events] if self.level == TraceLevel.VERBOSE else [],
        }
    
    def save_to_file(self, path: Path) -> None:
        """حفظ التتبع إلى ملف."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("trace_saved", trace_id=self.trace_id, path=str(path))


class ExecutionTraceManager:
    """مدير سجلات التنفيذ."""
    
    def __init__(
        self,
        enabled: bool = True,
        level: TraceLevel = TraceLevel.STANDARD,
        storage_path: Optional[Path] = None,
        persist_traces: bool = False,
    ) -> None:
        self.enabled = enabled
        self.level = level
        self.storage_path = storage_path
        self.persist_traces = persist_traces
        
        self._active_traces: Dict[str, ExecutionTrace] = {}
        self._completed_traces: List[ExecutionTrace] = []
        self._max_completed_traces: int = 100
    
    def start_trace(
        self,
        reasoning_id: str,
        problem: str,
        strategy: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionTrace:
        """بدء تتبع جديد."""
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4()),
            reasoning_id=reasoning_id,
            created_at=time.time(),
            problem=problem,
            strategy=strategy,
            context=context or {},
            level=self.level,
        )
        self._active_traces[reasoning_id] = trace
        
        self._log_event(
            trace,
            TraceEventType.ENGINE_START,
            "بدء محرك الاستدلال",
            f"بدء تتبع للمشكلة: {problem[:50]}...",
            success=True,
        )
        
        return trace
    
    def end_trace(
        self,
        reasoning_id: str,
        success: bool = True,
        final_confidence: float = 0.0,
    ) -> Optional[ExecutionTrace]:
        """إنهاء التتبع."""
        trace = self._active_traces.pop(reasoning_id, None)
        if not trace:
            logger.warning("trace_not_found", reasoning_id=reasoning_id)
            return None
        
        trace.complete(success=success, final_confidence=final_confidence)
        
        self._log_event(
            trace,
            TraceEventType.ENGINE_COMPLETE if success else TraceEventType.ENGINE_ERROR,
            "اكتمال محرك الاستدلال",
            f"انتهى التتبع بنجاح={success}",
            success=success,
            metadata={"final_confidence": final_confidence},
        )
        
        # تخزين التتبع المكتمل
        self._completed_traces.append(trace)
        if len(self._completed_traces) > self._max_completed_traces:
            self._completed_traces.pop(0)
        
        # حفظ إلى ملف إذا كان مفعلاً
        if self.persist_traces and self.storage_path:
            filename = f"trace_{trace.trace_id}.json"
            trace.save_to_file(self.storage_path / filename)
        
        logger.info(
            "trace_completed",
            trace_id=trace.trace_id,
            reasoning_id=reasoning_id,
            duration_ms=trace.total_duration_ms,
            success=success,
        )
        
        return trace
    
    def record_step(
        self,
        reasoning_id: str,
        step_name: str,
        step_number: int,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error: Optional[Exception] = None,
    ) -> None:
        """تسجيل خطوة."""
        trace = self._active_traces.get(reasoning_id)
        if not trace or not self.enabled:
            return
        
        event_type = (
            TraceEventType.STEP_COMPLETE if success else TraceEventType.STEP_ERROR
        )
        
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace.trace_id,
            event_type=event_type,
            timestamp=time.time(),
            step_number=step_number,
            duration_ms=None,
            success=success,
            event_name=step_name,
            description=f"خطوة {step_number}: {step_name}",
            input_data=input_data or {},
            output_data=output_data or {},
            error_message=str(error) if error else None,
            error_type=type(error).__name__ if error else None,
        )
        
        trace.add_event(event)
    
    def record_llm_call(
        self,
        reasoning_id: str,
        model: str,
        prompt_length: int,
        start_time: float,
        end_time: float,
        success: bool = True,
        error: Optional[Exception] = None,
        response_length: int = 0,
    ) -> None:
        """تسجيل استدعاء LLM."""
        trace = self._active_traces.get(reasoning_id)
        if not trace or not self.enabled:
            return
        
        duration_ms = (end_time - start_time) * 1000
        event_type = (
            TraceEventType.LLM_CALL_COMPLETE if success else TraceEventType.LLM_CALL_ERROR
        )
        
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace.trace_id,
            event_type=event_type,
            timestamp=start_time,
            duration_ms=duration_ms,
            step_number=None,
            success=success,
            event_name="llm_call",
            description=f"استدعاء LLM: {model}",
            input_data={
                "model": model,
                "prompt_length": prompt_length,
            },
            output_data={
                "response_length": response_length,
            },
            error_message=str(error) if error else None,
            error_type=type(error).__name__ if error else None,
            metadata={"model": model},
        )
        
        trace.add_event(event)
    
    def record_cache_access(
        self,
        reasoning_id: str,
        cache_key: str,
        hit: bool,
    ) -> None:
        """تسجيل وصول للـ cache."""
        trace = self._active_traces.get(reasoning_id)
        if not trace or not self.enabled:
            return
        
        event_type = TraceEventType.CACHE_HIT if hit else TraceEventType.CACHE_MISS
        
        self._log_event(
            trace,
            event_type,
            "cache_access",
            f"{'HIT' if hit else 'MISS'}: {cache_key[:30]}...",
            success=True,
            metadata={"cache_key": cache_key, "hit": hit},
        )
    
    def record_fallback(
        self,
        reasoning_id: str,
        original_strategy: str,
        fallback_strategy: str,
        reason: str,
    ) -> None:
        """تسجيل fallback."""
        trace = self._active_traces.get(reasoning_id)
        if not trace or not self.enabled:
            return
        
        self._log_event(
            trace,
            TraceEventType.FALLBACK_TRIGGERED,
            "fallback",
            f"تحويل من {original_strategy} إلى {fallback_strategy}",
            success=True,
            metadata={
                "original_strategy": original_strategy,
                "fallback_strategy": fallback_strategy,
                "reason": reason,
            },
        )
    
    def record_retry(
        self,
        reasoning_id: str,
        attempt: int,
        max_attempts: int,
        error: Optional[str] = None,
    ) -> None:
        """تسجيل محاولة إعادة."""
        trace = self._active_traces.get(reasoning_id)
        if not trace or not self.enabled:
            return
        
        self._log_event(
            trace,
            TraceEventType.RETRY_ATTEMPT,
            "retry",
            f"محاولة {attempt}/{max_attempts}",
            success=True,
            metadata={
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": error,
            },
        )
    
    def _log_event(
        self,
        trace: ExecutionTrace,
        event_type: TraceEventType,
        event_name: str,
        description: str,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        step_number: Optional[int] = None,
    ) -> None:
        """تسجيل حدث."""
        if not self.enabled:
            return
        
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace.trace_id,
            event_type=event_type,
            timestamp=time.time(),
            duration_ms=None,
            step_number=step_number,
            success=success,
            event_name=event_name,
            description=description,
            metadata=metadata or {},
        )
        
        trace.add_event(event)
    
    def get_trace(self, reasoning_id: str) -> Optional[ExecutionTrace]:
        """الحصول على تتبع معين."""
        return self._active_traces.get(reasoning_id)
    
    def get_recent_traces(self, limit: int = 10) -> List[ExecutionTrace]:
        """الحصول على آخر التتبعات."""
        return self._completed_traces[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات التتبع."""
        if not self._completed_traces:
            return {
                "total_traces": 0,
                "active_traces": len(self._active_traces),
                "avg_duration_ms": 0,
                "success_rate": 0,
            }
        
        completed = self._completed_traces
        successful = [t for t in completed if t.success]
        
        return {
            "total_traces": len(completed),
            "active_traces": len(self._active_traces),
            "successful_traces": len(successful),
            "failed_traces": len(completed) - len(successful),
            "success_rate": len(successful) / len(completed) if completed else 0,
            "avg_duration_ms": (
                sum(t.total_duration_ms or 0 for t in completed) / len(completed)
            ),
            "avg_llm_calls": sum(t.llm_calls_count for t in completed) / len(completed),
            "total_cache_hits": sum(t.cache_hits for t in completed),
            "total_cache_misses": sum(t.cache_misses for t in completed),
            "fallback_rate": (
                sum(1 for t in completed if t.fallback_triggered) / len(completed)
            ),
        }
