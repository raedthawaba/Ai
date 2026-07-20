"""
Metrics — نظام المقاييس الموحد
==============================

مقاييس شاملة ومحسّنة لمحرك الاستدلال.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MetricValue:
    """قيمة مقياس واحدة."""
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
        }


@dataclass
class TimingMetric:
    """مقياس توقيت."""
    operation: str
    duration_ms: float
    timestamp: float
    success: bool
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """جامع المقاييس."""
    
    # أنواع المقاييس المدعومة
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMING = "timing"
    
    def __init__(
        self,
        enabled: bool = True,
        prefix: str = "hajeen_brain",
        export_prometheus: bool = False,
    ) -> None:
        self.enabled = enabled
        self.prefix = prefix
        self.export_prometheus = export_prometheus
        
        # التخزين الداخلي
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timings: List[TimingMetric] = []
        
        # تتبع القيم
        self._all_metrics: List[MetricValue] = []
        self._max_stored_metrics: int = 10000
    
    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """زيادة عداد."""
        if not self.enabled:
            return
        
        key = self._make_key(name, labels)
        self._counters[key] += value
        
        self._record_metric(
            name=f"{self.prefix}_{name}",
            value=self._counters[key],
            labels=labels or {},
            metric_type=self.COUNTER,
        )
    
    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تعيين قيمة gauge."""
        if not self.enabled:
            return
        
        key = self._make_key(name, labels)
        self._gauges[key] = value
        
        self._record_metric(
            name=f"{self.prefix}_{name}",
            value=value,
            labels=labels or {},
            metric_type=self.GAUGE,
        )
    
    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل قيمة في histogram."""
        if not self.enabled:
            return
        
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        
        # الاحتفاظ بآخر 1000 قيمة فقط
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        
        self._record_metric(
            name=f"{self.prefix}_{name}",
            value=value,
            labels=labels or {},
            metric_type=self.HISTOGRAM,
        )
    
    def record_timing(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل توقيت عملية."""
        if not self.enabled:
            return
        
        timing = TimingMetric(
            operation=operation,
            duration_ms=duration_ms,
            timestamp=time.time(),
            success=success,
            labels=labels or {},
        )
        
        self._timings.append(timing)
        
        # الاحتفاظ بآخر 10000 توقيت
        if len(self._timings) > 10000:
            self._timings = self._timings[-10000:]
        
        # تسجيل في histogram
        self.observe_histogram(
            f"{operation}_duration_ms",
            duration_ms,
            labels,
        )
        
        # تسجيل النجاح/الفشل
        self.increment(
            f"{operation}_total",
            labels=labels,
        )
        if success:
            self.increment(
                f"{operation}_success",
                labels=labels,
            )
        else:
            self.increment(
                f"{operation}_errors",
                labels=labels,
            )
    
    def _record_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        metric_type: str,
    ) -> None:
        """تسجيل مقياس."""
        metric = MetricValue(
            name=name,
            value=value,
            timestamp=time.time(),
            labels=labels,
        )
        
        self._all_metrics.append(metric)
        
        # الحفاظ على الحد الأقصى
        if len(self._all_metrics) > self._max_stored_metrics:
            self._all_metrics = self._all_metrics[-self._max_stored_metrics:]
        
        # تصدير Prometheus إذا كان مفعلاً
        if self.export_prometheus:
            self._export_prometheus(name, value, labels, metric_type)
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """إنشاء مفتاح فريد للمقياس."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _export_prometheus(self, name: str, value: float, labels: Dict[str, str], metric_type: str) -> None:
        """تصدير إلى Prometheus."""
        # يمكن توسيع هذا لاحقاً
        pass
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """الحصول على قيمة عداد."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0.0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """الحصول على قيمة gauge."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0.0)
    
    def get_histogram_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, float]:
        """الحصول على إحصائيات histogram."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        
        if not values:
            return {
                "count": 0,
                "min": 0,
                "max": 0,
                "mean": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0,
            }
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        return {
            "count": n,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "mean": sum(sorted_values) / n,
            "p50": sorted_values[n // 2],
            "p95": sorted_values[int(n * 0.95)],
            "p99": sorted_values[int(n * 0.99)],
        }
    
    def get_timing_stats(self, operation: str) -> Dict[str, Any]:
        """الحصول على إحصائيات التوقيت."""
        timings = [t for t in self._timings if t.operation == operation]
        
        if not timings:
            return {
                "count": 0,
                "success_rate": 0,
                "avg_duration_ms": 0,
            }
        
        durations = [t.duration_ms for t in timings]
        successful = [t for t in timings if t.success]
        
        return {
            "count": len(timings),
            "success_count": len(successful),
            "success_rate": len(successful) / len(timings),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "avg_duration_ms": sum(durations) / len(durations),
        }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """الحصول على جميع الإحصائيات."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                key: self.get_histogram_stats(key)
                for key in self._histograms
            },
            "timing_operations": list(set(t.operation for t in self._timings)),
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص شامل."""
        # استدلالات
        total_reasoning = self.get_counter("reasoning_total")
        successful_reasoning = self.get_counter("reasoning_success")
        failed_reasoning = self.get_counter("reasoning_errors")
        
        # LLM
        total_llm_calls = self.get_counter("llm_call_total")
        llm_errors = self.get_counter("llm_call_errors")
        
        # Cache
        cache_hits = self.get_counter("cache_hit_total")
        cache_misses = self.get_counter("cache_miss_total")
        
        # الثقة
        confidence_stats = self.get_histogram_stats("reasoning_confidence")
        
        # التوقيت
        reasoning_timing = self.get_timing_stats("reasoning")
        
        return {
            "reasoning": {
                "total": total_reasoning,
                "successful": successful_reasoning,
                "failed": failed_reasoning,
                "success_rate": (
                    successful_reasoning / total_reasoning 
                    if total_reasoning > 0 else 0
                ),
            },
            "llm": {
                "total_calls": total_llm_calls,
                "errors": llm_errors,
                "error_rate": (
                    llm_errors / total_llm_calls 
                    if total_llm_calls > 0 else 0
                ),
            },
            "cache": {
                "hits": cache_hits,
                "misses": cache_misses,
                "hit_rate": (
                    cache_hits / (cache_hits + cache_misses)
                    if (cache_hits + cache_misses) > 0 else 0
                ),
            },
            "confidence": confidence_stats,
            "timing": reasoning_timing,
        }
    
    def reset(self) -> None:
        """إعادة تعيين جميع المقاييس."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timings.clear()
        self._all_metrics.clear()
        logger.info("metrics_reset")
    
    def export_prometheus_format(self) -> List[str]:
        """تصدير بصيغة Prometheus."""
        lines = []
        
        # Counters
        for key, value in self._counters.items():
            lines.append(f"# TYPE {key} counter")
            lines.append(f"{key} {value}")
        
        # Gauges
        for key, value in self._gauges.items():
            lines.append(f"# TYPE {key} gauge")
            lines.append(f"{key} {value}")
        
        # Histograms (كميات)
        for key, values in self._histograms.items():
            if values:
                lines.append(f"# TYPE {key} histogram")
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")
                lines.append(f"{key}_min {min(values)}")
                lines.append(f"{key}_max {max(values)}")
        
        return lines


# ── Singleton ─────────────────────────────────────────────────────────────────

_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """الحصول على جامع المقاييس."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def configure_metrics(
    enabled: bool = True,
    prefix: str = "hajeen_brain",
    export_prometheus: bool = False,
) -> MetricsCollector:
    """تكوين المقاييس."""
    global _metrics_collector
    _metrics_collector = MetricsCollector(
        enabled=enabled,
        prefix=prefix,
        export_prometheus=export_prometheus,
    )
    return _metrics_collector
