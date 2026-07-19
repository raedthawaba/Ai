"""
Observability Layer
==================

Provides comprehensive observability:
- Structured Logging
- Distributed Tracing
- Metrics Collection
- Health Checks

Usage:
    # Get logger
    logger = get_logger(__name__)
    logger.info("Request processed", extra={"request_id": "123"})
    
    # Create span
    with tracer.start_span("process_request") as span:
        span.set_attribute("request_id", "123")
        # do work
    
    # Record metric
    metrics.increment("requests_total", tags={"endpoint": "/api"})
    metrics.gauge("queue_size", 10)
"""

from __future__ import annotations

import logging
import time
import uuid
import json
from typing import (
    Any, Dict, List, Optional, Set, Callable,
    TypeVar, Generic
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from contextvars import ContextVar
import threading
from collections import defaultdict
import traceback

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# Context variables for request tracking
trace_id_ctx: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
span_id_ctx: ContextVar[Optional[str]] = ContextVar('span_id', default=None)


@dataclass
class LogRecord:
    """Structured log record."""
    timestamp: datetime
    level: str
    logger: str
    message: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "attributes": self.attributes,
            "error": self.error
        }


class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogger:
    """
    Structured logger with JSON output and context tracking.
    """
    
    _instances: Dict[str, StructuredLogger] = {}
    _lock = threading.Lock()
    
    def __init__(self, name: str):
        self.name = name
        self._logger = logging.getLogger(name)
        self._handlers: List[Callable] = []
        self._log_buffer: List[LogRecord] = []
        self._max_buffer_size = 1000
    
    @classmethod
    def get_logger(cls, name: str) -> StructuredLogger:
        """Get or create logger instance."""
        with cls._lock:
            if name not in cls._instances:
                cls._instances[name] = cls(name)
            return cls._instances[name]
    
    def add_handler(self, handler: Callable[[LogRecord], None]):
        """Add a log handler."""
        self._handlers.append(handler)
    
    def _create_record(
        self,
        level: str,
        message: str,
        attributes: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None
    ) -> LogRecord:
        """Create a log record."""
        record = LogRecord(
            timestamp=datetime.utcnow(),
            level=level,
            logger=self.name,
            message=message,
            trace_id=trace_id_ctx.get(),
            span_id=span_id_ctx.get(),
            attributes=attributes or {},
            error=str(error) if error else None
        )
        return record
    
    def _emit(self, record: LogRecord):
        """Emit a log record."""
        # Buffer
        self._log_buffer.append(record)
        if len(self._log_buffer) > self._max_buffer_size:
            self._log_buffer.pop(0)
        
        # Handlers
        for handler in self._handlers:
            try:
                handler(record)
            except Exception:
                pass
        
        # Standard logging
        extra = {
            "trace_id": record.trace_id,
            "span_id": record.span_id,
            **record.attributes
        }
        
        level_method = getattr(self._logger, record.level.lower())
        level_method(record.message, extra=extra)
    
    def debug(self, message: str, **attributes):
        """Log debug message."""
        self._emit(self._create_record("DEBUG", message, attributes))
    
    def info(self, message: str, **attributes):
        """Log info message."""
        self._emit(self._create_record("INFO", message, attributes))
    
    def warning(self, message: str, **attributes):
        """Log warning message."""
        self._emit(self._create_record("WARNING", message, attributes))
    
    def error(self, message: str, error: Optional[Exception] = None, **attributes):
        """Log error message."""
        self._emit(self._create_record("ERROR", message, attributes, error))
    
    def critical(self, message: str, error: Optional[Exception] = None, **attributes):
        """Log critical message."""
        self._emit(self._create_record("CRITICAL", message, attributes, error))
    
    def get_logs(
        self,
        since: Optional[datetime] = None,
        level: Optional[str] = None,
        limit: int = 100
    ) -> List[LogRecord]:
        """Get buffered logs."""
        logs = self._log_buffer
        
        if since:
            logs = [l for l in logs if l.timestamp >= since]
        
        if level:
            logs = [l for l in logs if l.level == level]
        
        return logs[-limit:]


def get_logger(name: str) -> StructuredLogger:
    """Get structured logger."""
    return StructuredLogger.get_logger(name)


# =============================================================================
# TRACING
# =============================================================================

@dataclass
class Span:
    """Distributed trace span."""
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "OK"  # OK, ERROR
    error_message: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0
    
    def set_attribute(self, key: str, value: Any):
        """Set span attribute."""
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add span event."""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow().isoformat(),
            "attributes": attributes or {}
        })
    
    def set_status(self, status: str, message: Optional[str] = None):
        """Set span status."""
        self.status = status
        self.error_message = message
    
    def record_exception(self, exception: Exception):
        """Record an exception."""
        self.status = "ERROR"
        self.error_message = str(exception)
        self.add_event("exception", {
            "type": type(exception).__name__,
            "message": str(exception),
            "traceback": traceback.format_exc()
        })
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
            "error_message": self.error_message
        }


class Tracer:
    """
    Distributed tracer for request tracing.
    """
    
    _instance: Optional[Tracer] = None
    
    def __init__(self, service_name: str = "hajeen"):
        self.service_name = service_name
        self._spans: Dict[str, Span] = {}
        self._span_stack: List[Span] = []
        self._handlers: List[Callable[[Span], None]] = []
        self._lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> Tracer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def start_span(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Start a new span."""
        # Get or create trace ID
        if not trace_id:
            trace_id = trace_id_ctx.get()
            if not trace_id:
                trace_id = str(uuid.uuid4())
                trace_id_ctx.set(trace_id)
        
        # Get parent from context or stack
        if not parent_id:
            if self._span_stack:
                parent = self._span_stack[-1]
                parent_id = parent.span_id
        
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=str(uuid.uuid4())[:16],
            parent_id=parent_id,
            attributes=attributes or {}
        )
        
        with self._lock:
            self._spans[span.span_id] = span
            self._span_stack.append(span)
        
        # Set context variables
        span_id_ctx.set(span.span_id)
        
        return span
    
    def end_span(self, span: Span, status: str = "OK"):
        """End a span."""
        span.end_time = time.time()
        
        if status != "OK":
            span.set_status(status)
        
        with self._lock:
            if self._span_stack and self._span_stack[-1] == span:
                self._span_stack.pop()
        
        # Process handlers
        for handler in self._handlers:
            try:
                handler(span)
            except Exception:
                pass
    
    def add_span_handler(self, handler: Callable[[Span], None]):
        """Add a span processor."""
        self._handlers.append(handler)
    
    def get_current_trace_id(self) -> Optional[str]:
        """Get current trace ID."""
        return trace_id_ctx.get()
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """Get span by ID."""
        return self._spans.get(span_id)
    
    def get_trace(self, trace_id: str) -> List[Span]:
        """Get all spans for a trace."""
        return [
            s for s in self._spans.values()
            if s.trace_id == trace_id
        ]
    
    def clear_finished_spans(self, older_than_seconds: int = 3600):
        """Clear old finished spans."""
        cutoff = time.time() - older_than_seconds
        with self._lock:
            to_remove = [
                sid for sid, span in self._spans.items()
                if span.end_time and span.end_time < cutoff
            ]
            for sid in to_remove:
                del self._spans[sid]


class SpanContext:
    """Context manager for spans."""
    
    def __init__(
        self,
        tracer: Tracer,
        name: str,
        attributes: Optional[Dict[str, Any]] = None
    ):
        self.tracer = tracer
        self.name = name
        self.attributes = attributes
        self.span: Optional[Span] = None
    
    def __enter__(self) -> Span:
        self.span = self.tracer.start_span(self.name, attributes=self.attributes)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_val:
                self.span.record_exception(exc_val)
                self.tracer.end_span(self.span, status="ERROR")
            else:
                self.tracer.end_span(self.span, status="OK")
        return False


def get_tracer() -> Tracer:
    """Get global tracer."""
    return Tracer.get_instance()


def trace(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Decorator/context manager for tracing."""
    tracer = get_tracer()
    
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            with tracer.start_span(name, attributes=attributes) as span:
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    raise
        return async_wrapper
    return decorator


# =============================================================================
# METRICS
# =============================================================================

@dataclass
class MetricPoint:
    """Single metric point."""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Metrics collector for observability.
    """
    
    _instance: Optional[MetricsCollector] = None
    
    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._series: Dict[str, List[MetricPoint]] = defaultdict(list)
        self._handlers: List[Callable[[str, float, Dict], None]] = []
        self._lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> MetricsCollector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def increment(
        self,
        name: str,
        value: float = 1,
        tags: Optional[Dict[str, str]] = None
    ):
        """Increment a counter."""
        key = self._make_key(name, tags)
        with self._lock:
            self._counters[key] += value
        
        self._emit("counter", name, value, tags)
    
    def decrement(
        self,
        name: str,
        value: float = 1,
        tags: Optional[Dict[str, str]] = None
    ):
        """Decrement a counter."""
        self.increment(name, -value, tags)
    
    def gauge(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """Set a gauge value."""
        key = self._make_key(name, tags)
        with self._lock:
            self._gauges[key] = value
        
        self._emit("gauge", name, value, tags)
    
    def histogram(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """Record a histogram value."""
        key = self._make_key(name, tags)
        with self._lock:
            self._histograms[key].append(value)
        
        self._emit("histogram", name, value, tags)
    
    def timing(
        self,
        name: str,
        duration_ms: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """Record a timing metric."""
        self.histogram(f"{name}.duration_ms", duration_ms, tags)
    
    def _emit(self, metric_type: str, name: str, value: float, tags: Optional[Dict[str, str]]):
        """Emit metric to handlers."""
        for handler in self._handlers:
            try:
                handler(metric_type, name, value, tags or {})
            except Exception:
                pass
    
    def add_handler(self, handler: Callable[[str, str, float, Dict], None]):
        """Add metric handler."""
        self._handlers.append(handler)
    
    def _make_key(self, name: str, tags: Optional[Dict[str, str]]) -> str:
        """Create metric key from name and tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"
    
    def get_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> float:
        """Get counter value."""
        key = self._make_key(name, tags)
        return self._counters.get(key, 0)
    
    def get_gauge(self, name: str, tags: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get gauge value."""
        key = self._make_key(name, tags)
        return self._gauges.get(key)
    
    def get_histogram_stats(
        self,
        name: str,
        tags: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, tags)
        values = self._histograms.get(key, [])
        
        if not values:
            return {"count": 0}
        
        sorted_values = sorted(values)
        count = len(sorted_values)
        
        return {
            "count": count,
            "sum": sum(sorted_values),
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "avg": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p95": sorted_values[int(count * 0.95)],
            "p99": sorted_values[int(count * 0.99)]
        }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: len(v) for k, v in self._histograms.items()
                }
            }
    
    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    return MetricsCollector.get_instance()


# Convenience metrics functions
def increment(name: str, value: float = 1, **tags):
    """Increment a counter."""
    get_metrics().increment(name, value, tags)

def gauge(name: str, value: float, **tags):
    """Set a gauge."""
    get_metrics().gauge(name, value, tags)

def timing(name: str, duration_ms: float, **tags):
    """Record timing."""
    get_metrics().timing(name, duration_ms, tags)


# =============================================================================
# HEALTH CHECKS
# =============================================================================

class HealthCheck:
    """Health check interface."""
    
    def __init__(
        self,
        name: str,
        check: Callable[[], bool],
        timeout: float = 5
    ):
        self.name = name
        self.check = check
        self.timeout = timeout
        self.last_result: Optional[bool] = None
        self.last_check_time: Optional[float] = None
    
    async def run(self) -> Dict[str, Any]:
        """Run health check."""
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(self.check):
                result = await asyncio.wait_for(self.check(), timeout=self.timeout)
            else:
                result = self.check()
            
            self.last_result = result
            self.last_check_time = time.time()
            
            return {
                "name": self.name,
                "status": "healthy" if result else "unhealthy",
                "latency_ms": (time.time() - start) * 1000
            }
        except Exception as e:
            self.last_result = False
            self.last_check_time = time.time()
            
            return {
                "name": self.name,
                "status": "unhealthy",
                "error": str(e),
                "latency_ms": (time.time() - start) * 1000
            }


class HealthCheckRegistry:
    """Registry for health checks."""
    
    def __init__(self):
        self._checks: Dict[str, HealthCheck] = {}
    
    def register(
        self,
        name: str,
        check: Callable[[], bool],
        timeout: float = 5
    ):
        """Register a health check."""
        self._checks[name] = HealthCheck(name, check, timeout)
    
    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks."""
        results = {}
        all_healthy = True
        
        for name, check in self._checks.items():
            result = await check.run()
            results[name] = result
            if result["status"] != "healthy":
                all_healthy = False
        
        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "checks": results,
            "timestamp": datetime.utcnow().isoformat()
        }


# Global health registry
_health_registry: Optional[HealthCheckRegistry] = None

def get_health_registry() -> HealthCheckRegistry:
    global _health_registry
    if _health_registry is None:
        _health_registry = HealthCheckRegistry()
    return _health_registry
