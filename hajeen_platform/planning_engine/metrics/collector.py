"""Planning Engine - Metrics Collection System."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class MetricType(str, Enum):
    """أنواع المقاييس."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    TIMER = "timer"


@dataclass
class MetricValue:
    """قيمة مقياس واحدة."""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class Metric:
    """تعريف مقياس."""
    name: str
    metric_type: MetricType
    description: str = ""
    unit: str = ""
    labels: List[str] = field(default_factory=list)
    
    # للعدادات
    value: float = 0.0
    
    # للـ gauges
    last_value: float = 0.0
    
    # للـ histograms
    buckets: Dict[float, int] = field(default_factory=lambda: {
        0.005: 0, 0.01: 0, 0.025: 0, 0.05: 0, 0.1: 0,
        0.25: 0, 0.5: 0, 1.0: 0, 2.5: 0, 5.0: 0, 10.0: 0,
    })
    sum: float = 0.0
    count: int = 0
    
    # للتوقيت
    _start_time: Optional[float] = field(default=None, repr=False)


class MetricsCollector:
    """
    جامع المقاييس المركزي.
    
    الميزات:
    - عدادات (Counters)
    - مقاييس فورية (Gauges)
    - مخططات توزيع (Histograms)
    - ملخصات (Summaries)
    - مؤقتات (Timers)
    - تجميع حسب labels
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, Metric] = {}
        self._values: Dict[str, List[MetricValue]] = defaultdict(list)
        self._max_values_per_metric = 10000
        self._lock = asyncio.Lock()
        self._callbacks: List[Callable[[str, float, Dict[str, str]], None]] = []

    def register_metric(
        self,
        name: str,
        metric_type: MetricType,
        description: str = "",
        unit: str = "",
        labels: Optional[List[str]] = None,
    ) -> None:
        """تسجيل مقياس جديد."""
        if name in self._metrics:
            logger.warning("metrics: metric already registered", name=name)
            return
        
        self._metrics[name] = Metric(
            name=name,
            metric_type=metric_type,
            description=description,
            unit=unit,
            labels=labels or [],
        )
        logger.debug("metrics: registered", name=name, type=metric_type.value)

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """زيادة عداد."""
        self._update_metric(name, value, labels or {}, MetricType.COUNTER)

    def gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تعيين قيمة gauge."""
        self._update_metric(name, value, labels or {}, MetricType.GAUGE)

    def histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل قيمة في histogram."""
        self._update_metric(name, value, labels or {}, MetricType.HISTOGRAM)

    def summary(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل قيمة في summary."""
        self._update_metric(name, value, labels or {}, MetricType.SUMMARY)

    def timer(self, name: str) -> Callable[[], float]:
        """مؤقت للسياق."""
        start = time.time()
        
        def stop() -> float:
            duration_ms = (time.time() - start) * 1000
            self.histogram(f"{name}_duration_ms", duration_ms)
            return duration_ms
        
        return stop

    @contextmanager
    def timed(self, name: str, labels: Optional[Dict[str, str]] = None):
        """سياق للتوقيت التلقائي."""
        start = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start) * 1000
            self.histogram(f"{name}_duration_ms", duration_ms, labels)

    def _update_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        metric_type: MetricType,
    ) -> None:
        """تحديث مقياس."""
        if name not in self._metrics:
            self.register_metric(name, metric_type)
        
        metric = self._metrics[name]
        metric_value = MetricValue(
            timestamp=time.time(),
            value=value,
            labels=labels,
        )
        
        # تحديث القيم
        if metric_type == MetricType.COUNTER:
            metric.value += value
            metric.last_value = metric.value
        elif metric_type == MetricType.GAUGE:
            metric.last_value = value
        elif metric_type in (MetricType.HISTOGRAM, MetricType.SUMMARY):
            metric.sum += value
            metric.count += 1
            metric.last_value = value
            
            # تحديث الـ buckets للـ histogram
            if metric_type == MetricType.HISTOGRAM:
                for bucket_limit in sorted(metric.buckets.keys()):
                    if value <= bucket_limit:
                        metric.buckets[bucket_limit] += 1
        
        # تخزين القيم التاريخية
        key = self._get_metric_key(name, labels)
        self._values[key].append(metric_value)
        
        # تقييد عدد القيم
        if len(self._values[key]) > self._max_values_per_metric:
            self._values[key] = self._values[key][-self._max_values_per_metric:]
        
        # إشعار الـ callbacks
        for callback in self._callbacks:
            try:
                callback(name, value, labels)
            except Exception as e:
                logger.error("metrics: callback error", error=str(e))

    def _get_metric_key(self, name: str, labels: Dict[str, str]) -> str:
        """إنشاء مفتاح فريد للمقياس."""
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name

    def add_callback(self, callback: Callable[[str, float, Dict[str, str]], None]) -> None:
        """إضافة callback للتحديثات."""
        self._callbacks.append(callback)

    def get(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """الحصول على قيمة مقياس."""
        if name not in self._metrics:
            return None
        
        metric = self._metrics[name]
        key = self._get_metric_key(name, labels or {})
        
        if metric.metric_type == MetricType.COUNTER:
            return metric.value
        elif metric.metric_type == MetricType.GAUGE:
            return metric.last_value
        elif metric.metric_type in (MetricType.HISTOGRAM, MetricType.SUMMARY):
            return metric.last_value
        
        return None

    def get_all(self) -> Dict[str, Any]:
        """الحصول على جميع المقاييس."""
        result: Dict[str, Any] = {}
        
        for name, metric in self._metrics.items():
            result[name] = {
                "type": metric.metric_type.value,
                "description": metric.description,
                "unit": metric.unit,
            }
            
            if metric.metric_type == MetricType.COUNTER:
                result[name]["value"] = metric.value
            elif metric.metric_type == MetricType.GAUGE:
                result[name]["value"] = metric.last_value
            elif metric.metric_type in (MetricType.HISTOGRAM, MetricType.SUMMARY):
                result[name]["count"] = metric.count
                result[name]["sum"] = metric.sum
                result[name]["last_value"] = metric.last_value
                if metric.metric_type == MetricType.HISTOGRAM:
                    result[name]["buckets"] = metric.buckets
        
        return result

    def get_history(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        since: Optional[float] = None,
    ) -> List[MetricValue]:
        """الحصول على تاريخ القيم."""
        key = self._get_metric_key(name, labels or {})
        values = self._values.get(key, [])
        
        if since:
            values = [v for v in values if v.timestamp >= since]
        
        return values

    def export_prometheus(self) -> str:
        """تصدير بصيغة Prometheus."""
        lines: List[str] = []
        
        for name, metric in self._metrics.items():
            # إضافة التعليقات
            if metric.description:
                lines.append(f"# HELP {name} {metric.description}")
            if metric.unit:
                lines.append(f"# UNIT {name} {metric.unit}")
            lines.append(f"# TYPE {name} {metric.metric_type.value}")
            
            if metric.metric_type == MetricType.COUNTER:
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}{labels_str} {metric.value}")
                
            elif metric.metric_type == MetricType.GAUGE:
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}{labels_str} {metric.last_value}")
                
            elif metric.metric_type == MetricType.HISTOGRAM:
                labels_str = self._format_labels(metric.labels)
                total = sum(metric.buckets.values())
                lines.append(f"{name}_sum{labels_str} {metric.sum}")
                lines.append(f"{name}_count{labels_str} {metric.count}")
                cumulative = 0
                for bucket, count in sorted(metric.buckets.items()):
                    cumulative += count
                    bucket_labels = dict(metric.labels) if metric.labels else {}
                    bucket_labels["le"] = str(bucket)
                    bucket_labels_str = self._format_labels(bucket_labels)
                    lines.append(f"{name}_bucket{bucket_labels_str} {cumulative}")
                lines.append(f"{name}_bucket{{le=\"+Inf\"}} {total}")
        
        return "\n".join(lines)

    def _format_labels(self, labels: Dict[str, str]) -> str:
        """تنسيق الـ labels."""
        if not labels:
            return ""
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{{{label_str}}}"

    def reset(self, name: Optional[str] = None) -> None:
        """إعادة تعيين مقياس أو جميع المقاييس."""
        if name:
            if name in self._metrics:
                metric = self._metrics[name]
                metric.value = 0
                metric.last_value = 0
                metric.sum = 0
                metric.count = 0
                metric.buckets = {k: 0 for k in metric.buckets}
            self._values.pop(name, None)
        else:
            for metric in self._metrics.values():
                metric.value = 0
                metric.last_value = 0
                metric.sum = 0
                metric.count = 0
                metric.buckets = {k: 0 for k in metric.buckets}
            self._values.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات."""
        return {
            "total_metrics": len(self._metrics),
            "total_values": sum(len(v) for v in self._values.values()),
            "metrics_by_type": {
                mtype.value: sum(1 for m in self._metrics.values() if m.metric_type == mtype)
                for mtype in MetricType
            },
        }


from contextlib import contextmanager


# Singleton instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """الحصول على جامع المقاييس الوحيد."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


# Business metrics helpers
class BusinessMetrics:
    """مقاييس الأعمال."""

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector or get_metrics_collector()
        self._register_metrics()

    def _register_metrics(self) -> None:
        """تسجيل مقاييس الأعمال."""
        metrics = [
            ("plans_created_total", MetricType.COUNTER, "Total plans created"),
            ("plans_completed_total", MetricType.COUNTER, "Total plans completed"),
            ("plans_failed_total", MetricType.COUNTER, "Total plans failed"),
            ("steps_executed_total", MetricType.COUNTER, "Total steps executed"),
            ("steps_failed_total", MetricType.COUNTER, "Total steps failed"),
            ("active_plans", MetricType.GAUGE, "Currently active plans"),
            ("plan_execution_duration_ms", MetricType.HISTOGRAM, "Plan execution duration in ms"),
            ("step_execution_duration_ms", MetricType.HISTOGRAM, "Step execution duration in ms"),
        ]
        
        for name, mtype, desc in metrics:
            self._collector.register_metric(name, mtype, desc)

    def plan_created(self, **labels: str) -> None:
        """تسجيل إنشاء خطة."""
        self._collector.counter("plans_created_total", 1, labels)

    def plan_completed(self, duration_ms: float, **labels: str) -> None:
        """تسجيل إكمال خطة."""
        self._collector.counter("plans_completed_total", 1, labels)
        self._collector.histogram("plan_execution_duration_ms", duration_ms, labels)

    def plan_failed(self, **labels: str) -> None:
        """تسجيل فشل خطة."""
        self._collector.counter("plans_failed_total", 1, labels)

    def step_executed(self, duration_ms: float, success: bool, **labels: str) -> None:
        """تسجيل تنفيذ خطوة."""
        self._collector.counter("steps_executed_total", 1, labels)
        self._collector.histogram("step_execution_duration_ms", duration_ms, labels)
        if not success:
            self._collector.counter("steps_failed_total", 1, labels)

    def set_active_plans(self, count: int) -> None:
        """تعيين عدد الخطط النشطة."""
        self._collector.gauge("active_plans", float(count))


# Performance metrics helpers
class PerformanceMetrics:
    """مقاييس الأداء."""

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector or get_metrics_collector()
        self._register_metrics()

    def _register_metrics(self) -> None:
        """تسجيل مقاييس الأداء."""
        metrics = [
            ("engine_cpu_usage_percent", MetricType.GAUGE, "Engine CPU usage percent"),
            ("engine_memory_usage_bytes", MetricType.GAUGE, "Engine memory usage bytes"),
            ("concurrent_plans", MetricType.GAUGE, "Number of concurrent plans"),
            ("queue_depth", MetricType.GAUGE, "Queue depth"),
            ("cache_hit_ratio", MetricType.GAUGE, "Cache hit ratio"),
            ("api_request_duration_ms", MetricType.HISTOGRAM, "API request duration in ms"),
        ]
        
        for name, mtype, desc in metrics:
            self._collector.register_metric(name, mtype, desc)

    def set_cpu_usage(self, percent: float) -> None:
        """تعيين استخدام CPU."""
        self._collector.gauge("engine_cpu_usage_percent", percent)

    def set_memory_usage(self, bytes: float) -> None:
        """تعيين استخدام الذاكرة."""
        self._collector.gauge("engine_memory_usage_bytes", bytes)

    def set_concurrent_plans(self, count: int) -> None:
        """تعيين عدد الخطط المتزامنة."""
        self._collector.gauge("concurrent_plans", float(count))

    def set_queue_depth(self, depth: int) -> None:
        """تعيين عمق الطابور."""
        self._collector.gauge("queue_depth", float(depth))

    def set_cache_hit_ratio(self, ratio: float) -> None:
        """تعيين نسبة إصابة الـ cache."""
        self._collector.gauge("cache_hit_ratio", ratio)

    def record_api_request(self, duration_ms: float, status_code: int) -> None:
        """تسجيل طلب API."""
        labels = {"status": str(status_code)}
        self._collector.histogram("api_request_duration_ms", duration_ms, labels)
