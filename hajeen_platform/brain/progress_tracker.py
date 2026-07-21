"""
Progress Tracker + Performance Metrics
======================================
تتبع التقدم وحساب ETA وتحليل الأداء.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    task_id: str
    task_name: str
    status: TaskStatus
    progress_percent: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_completion: Optional[float] = None
    actual_duration: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProgressReport:
    report_id: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    running_tasks: int
    pending_tasks: int
    overall_progress: float  # 0-100
    estimated_time_remaining: float  # seconds
    estimated_completion_time: Optional[float]
    throughput: float  # tasks per minute
    average_task_duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProgressTracker:
    """
    يتتبع تقدم تنفيذ المهام ويحسب ETA.
    
    المميزات:
    - تتبع حالة كل مهمة
    - حساب التقدم الكلي
    - تقدير وقت الإنجاز (ETA)
    - قياس الإنتاجية (throughput)
    - تحليل الأداء
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskProgress] = {}
        self._completed_durations: List[float] = []
        self._start_time: Optional[float] = None
        self._last_update: float = time.time()

    def start_tracking(self, task_id: str, task_name: str, metadata: Optional[Dict] = None) -> None:
        """بدء تتبع مهمة."""
        self._tasks[task_id] = TaskProgress(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.RUNNING,
            progress_percent=0.0,
            started_at=time.time(),
            metadata=metadata or {},
        )
        if self._start_time is None:
            self._start_time = time.time()
        logger.info("progress_tracker: started task %s - %s", task_id, task_name)

    def update_progress(self, task_id: str, progress_percent: float) -> None:
        """تحديث تقدم مهمة."""
        if task_id in self._tasks:
            self._tasks[task_id].progress_percent = min(100.0, max(0.0, progress_percent))

    def complete_task(self, task_id: str) -> None:
        """إكمال مهمة."""
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.status = TaskStatus.COMPLETED
            task.progress_percent = 100.0
            task.completed_at = time.time()
            
            if task.started_at:
                task.actual_duration = task.completed_at - task.started_at
                self._completed_durations.append(task.actual_duration)
            
            logger.info(
                "progress_tracker: completed task %s in %.2fs",
                task_id, task.actual_duration or 0
            )

    def fail_task(self, task_id: str, error: Optional[str] = None) -> None:
        """فشل مهمة."""
        if task_id in self._tasks:
            self._tasks[task_id].status = TaskStatus.FAILED
            self._tasks[task_id].completed_at = time.time()
            if error:
                self._tasks[task_id].metadata["error"] = error
            logger.warning("progress_tracker: failed task %s - %s", task_id, error)

    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """الحصول على تقدم مهمة."""
        return self._tasks.get(task_id)

    def get_report(self) -> ProgressReport:
        """إنشاء تقرير التقدم."""
        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        running = sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)

        total = len(self._tasks)
        overall_progress = (completed / total * 100) if total > 0 else 0.0

        # حساب ETA
        avg_duration = sum(self._completed_durations) / len(self._completed_durations) if self._completed_durations else 0
        remaining_tasks = total - completed - failed
        eta = avg_duration * remaining_tasks if avg_duration > 0 else 0

        # حساب الإنتاجية
        elapsed = time.time() - self._start_time if self._start_time else 1
        throughput = (completed / elapsed * 60) if elapsed > 0 else 0  # tasks per minute

        # وقت الإنجاز المتوقع
        completion_time = time.time() + eta if eta > 0 else None

        return ProgressReport(
            report_id=str(uuid.uuid4()),
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=failed,
            running_tasks=running,
            pending_tasks=pending,
            overall_progress=overall_progress,
            estimated_time_remaining=eta,
            estimated_completion_time=completion_time,
            throughput=throughput,
            average_task_duration=avg_duration,
            metadata={
                "elapsed_seconds": elapsed,
                "last_update": time.time(),
            },
        )

    def get_all_tasks(self) -> List[TaskProgress]:
        """الحصول على جميع المهام."""
        return list(self._tasks.values())

    def reset(self) -> None:
        """إعادة تعيين المتتبع."""
        self._tasks.clear()
        self._completed_durations.clear()
        self._start_time = None
        logger.info("progress_tracker: reset")


class PerformanceAnalyzer:
    """
    يحلل أداء النظام ويقترح تحسينات.
    """

    def __init__(self) -> None:
        self._historical_metrics: List[Dict[str, Any]] = []

    def analyze_performance(
        self,
        metrics_summary: Dict[str, Any],
        task_durations: List[float],
    ) -> Dict[str, Any]:
        """تحليل الأداء."""
        if not task_durations:
            return {
                "status": "no_data",
                "recommendations": ["لا توجد بيانات كافية للتحليل"],
            }

        avg_duration = sum(task_durations) / len(task_durations)
        min_duration = min(task_durations)
        max_duration = max(task_durations)

        # حساب الانحراف المعياري
        variance = sum((d - avg_duration) ** 2 for d in task_durations) / len(task_durations)
        std_dev = variance ** 0.5

        # تحديد الأداء
        performance_level = "good"
        if std_dev / avg_duration > 0.5:
            performance_level = "unstable"
        elif avg_duration > metrics_summary.get("expected_duration", 300):
            performance_level = "slow"

        # اقتراحات التحسين
        recommendations = []
        if performance_level == "slow":
            recommendations.append("النظام بطيء - فكر في parallelization")
        if performance_level == "unstable":
            recommendations.append("التباين عالي - تحقق من الموارد")
        if avg_duration > 60:
            recommendations.append("متوسط وقت المهمة مرتفع - فكر في تحسين الخوارزميات")
        if not recommendations:
            recommendations.append("الأداء جيد")

        return {
            "performance_level": performance_level,
            "avg_duration": round(avg_duration, 2),
            "min_duration": round(min_duration, 2),
            "max_duration": round(max_duration, 2),
            "std_deviation": round(std_dev, 2),
            "recommendations": recommendations,
        }

    def record_metrics(self, metrics: Dict[str, Any]) -> None:
        """تسجيل المقاييس."""
        metrics["timestamp"] = time.time()
        self._historical_metrics.append(metrics)
        # احتفظ بآخر 1000 سجل
        if len(self._historical_metrics) > 1000:
            self._historical_metrics = self._historical_metrics[-1000:]

    def get_historical_analysis(self, window_minutes: int = 60) -> Dict[str, Any]:
        """تحليل تاريخي."""
        cutoff = time.time() - (window_minutes * 60)
        recent = [m for m in self._historical_metrics if m.get("timestamp", 0) > cutoff]

        if not recent:
            return {"status": "no_data", "window_minutes": window_minutes}

        return {
            "window_minutes": window_minutes,
            "samples": len(recent),
            "avg_throughput": sum(m.get("throughput", 0) for m in recent) / len(recent),
            "avg_latency": sum(m.get("latency", 0) for m in recent) / len(recent),
        }


# Singleton instances
_tracker: Optional[ProgressTracker] = None
_analyzer: Optional[PerformanceAnalyzer] = None


def get_progress_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProgressTracker()
    return _tracker


def get_performance_analyzer() -> PerformanceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = PerformanceAnalyzer()
    return _analyzer
