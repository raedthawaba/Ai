"""Planning Engine Core - Types and Enums."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class PlanStatus(str, Enum):
    """حالات الخطة."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class PlanPriority(int, Enum):
    """أولويات الخطة."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class ExecutionState(str, Enum):
    """حالات التنفيذ."""
    IDLE = "idle"
    PREPARING = "preparing"
    EXECUTING = "executing"
    WAITING = "waiting"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlanContext:
    """سياق الخطة - معلومات إضافية."""
    goal: Optional[str] = None  # الهدف من الخطة
    constraints: Optional[List[str]] = None  # القيود
    priority: PlanPriority = PlanPriority.MEDIUM  # الأولوية
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStep:
    """خطوة تنفيذ واحدة."""
    step_id: str
    name: str
    description: str
    state: ExecutionState
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class Plan:
    """خطة تنفيذ كاملة."""
    plan_id: str
    name: str
    description: str
    status: PlanStatus
    priority: PlanPriority
    created_at: datetime
    updated_at: datetime
    context: PlanContext
    steps: List[ExecutionStep] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    total_duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.priority, int):
            self.priority = PlanPriority(self.priority)
        if isinstance(self.status, str):
            self.status = PlanStatus(self.status)
        if self.plan_id is None:
            self.plan_id = str(uuid.uuid4())

    def add_step(self, step: ExecutionStep) -> None:
        """إضافة خطوة للخطة."""
        self.steps.append(step)
        self.updated_at = datetime.utcnow()

    def complete_step(self, step_id: str, result: Any = None) -> None:
        """إكمال خطوة."""
        for step in self.steps:
            if step.step_id == step_id:
                step.state = ExecutionState.COMPLETED
                step.completed_at = datetime.utcnow()
                step.result = result
                if step.started_at:
                    step.duration_ms = (step.completed_at - step.started_at).total_seconds() * 1000
                if step_id not in self.completed_steps:
                    self.completed_steps.append(step_id)
                break
        self.updated_at = datetime.utcnow()

    def fail_step(self, step_id: str, error: str) -> None:
        """فشل خطوة."""
        for step in self.steps:
            if step.step_id == step_id:
                step.state = ExecutionState.FAILED
                step.completed_at = datetime.utcnow()
                step.error = error
                if step.started_at:
                    step.duration_ms = (step.completed_at - step.started_at).total_seconds() * 1000
                if step_id not in self.failed_steps:
                    self.failed_steps.append(step_id)
                break
        self.updated_at = datetime.utcnow()

    def retry_step(self, step_id: str) -> bool:
        """إعادة محاولة خطوة."""
        for step in self.steps:
            if step.step_id == step_id and step.retry_count < step.max_retries:
                step.retry_count += 1
                step.state = ExecutionState.IDLE
                step.error = None
                if step_id in self.failed_steps:
                    self.failed_steps.remove(step_id)
                self.updated_at = datetime.utcnow()
                return True
        return False

    def is_complete(self) -> bool:
        """التحقق من اكتمال الخطة."""
        return all(s.state == ExecutionState.COMPLETED for s in self.steps)

    def has_failures(self) -> bool:
        """التحقق من وجود فشل."""
        return any(s.state == ExecutionState.FAILED for s in self.steps)

    def get_progress(self) -> float:
        """الحصول على نسبة التقدم."""
        if not self.steps:
            return 0.0
        completed = len([s for s in self.steps if s.state == ExecutionState.COMPLETED])
        return (completed / len(self.steps)) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "steps": [s.to_dict() for s in self.steps],
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "total_duration_ms": self.total_duration_ms,
            "progress": self.get_progress(),
            "metadata": self.metadata,
        }


@dataclass
class ExecutionResult:
    """نتيجة تنفيذ الخطة."""
    plan_id: str
    success: bool
    completed_steps: int
    failed_steps: int
    total_duration_ms: float
    errors: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # حقول تؤثر على Decision Engine
    priority: Optional[PlanPriority] = None  # أولوية الخطة
    context: Optional[PlanContext] = None  # سياق الخطة
    step_names: List[str] = field(default_factory=list)  # أسماء الخطوات
    required_capabilities: List[str] = field(default_factory=list)  # القدرات المطلوبة
    estimated_complexity: int = 1  # التعقيد التقديري (1-5)
    
    @property
    def result_id(self) -> str:
        """معرف النتيجة."""
        return self.plan_id
    
    @property
    def complexity_score(self) -> float:
        """درجة التعقيد بناءً على الخطوات."""
        return min(self.completed_steps / 5.0, 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "result_id": self.result_id,
            "success": self.success,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "total_duration_ms": self.total_duration_ms,
            "priority": self.priority.value if self.priority else None,
            "complexity_score": self.complexity_score,
            "required_capabilities": self.required_capabilities,
            "errors": self.errors,
            "results": self.results,
            "metadata": self.metadata,
        }
