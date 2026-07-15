"""
Task Decomposer — مفكّك المهام إلى وحدات مستقلة
=================================================
يحوّل كل هدف إلى قائمة مهام صغيرة مستقلة قابلة للجدولة والتتبع.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .goal_manager import Goal, IntentType, ComplexityLevel

logger = logging.getLogger(__name__)


class TaskPriority(int, Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


@dataclass
class MicroTask:
    """وحدة التنفيذ الأصغر — مستقلة وقابلة للجدولة."""
    task_id: str
    name: str
    description: str
    priority: TaskPriority
    execution_mode: ExecutionMode
    depends_on: List[str]          # task_ids المهام السابقة
    assigned_model: Optional[str]  # النموذج المخصص (إن وُجد)
    assigned_tool: Optional[str]   # الأداة المخصصة (إن وُجدت)
    estimated_tokens: int
    max_retries: int
    timeout_seconds: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "execution_mode": self.execution_mode,
            "depends_on": self.depends_on,
            "assigned_model": self.assigned_model,
            "assigned_tool": self.assigned_tool,
            "estimated_tokens": self.estimated_tokens,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class DecompositionPlan:
    plan_id: str
    goal_id: str
    tasks: List[MicroTask]
    total_estimated_tokens: int
    estimated_duration_seconds: float
    can_parallelize: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def get_execution_order(self) -> List[List[MicroTask]]:
        """ترتيب المهام في طبقات (كل طبقة تعمل بالتوازي)."""
        resolved: set = set()
        layers: List[List[MicroTask]] = []
        remaining = list(self.tasks)

        while remaining:
            layer = [t for t in remaining if all(d in resolved for d in t.depends_on)]
            if not layer:
                # Circular dependency fallback — أضف الجميع
                layer = remaining
            for t in layer:
                resolved.add(t.task_id)
            layers.append(layer)
            remaining = [t for t in remaining if t.task_id not in resolved]

        return layers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "tasks": [t.to_dict() for t in self.tasks],
            "total_estimated_tokens": self.total_estimated_tokens,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "can_parallelize": self.can_parallelize,
            "execution_layers": len(self.get_execution_order()),
        }


class TaskDecomposer:
    """
    يستقبل Goal ويولّد DecompositionPlan.
    كل مهمة فرعية مستقلة مع تبعيات واضحة.
    """

    def __init__(self) -> None:
        self._plans: Dict[str, DecompositionPlan] = {}

    async def decompose(self, goal: Goal) -> DecompositionPlan:
        """تفكيك الهدف إلى مهام صغيرة."""
        tasks = self._build_tasks(goal)
        total_tokens = sum(t.estimated_tokens for t in tasks)
        # تقدير زمن التنفيذ: 1 ثانية لكل 100 token + 2ث لكل مهمة
        duration = (total_tokens / 100) + (len(tasks) * 2)

        plan = DecompositionPlan(
            plan_id=str(uuid.uuid4()),
            goal_id=goal.goal_id,
            tasks=tasks,
            total_estimated_tokens=total_tokens,
            estimated_duration_seconds=duration,
            can_parallelize=goal.complexity in (ComplexityLevel.COMPLEX, ComplexityLevel.ENTERPRISE),
            metadata={"intent": goal.intent, "domain": goal.domain},
        )
        self._plans[plan.plan_id] = plan
        logger.info(
            "task_decomposer: goal=%s → %d tasks, tokens≈%d, duration≈%.1fs",
            goal.goal_id, len(tasks), total_tokens, duration
        )
        return plan

    def _build_tasks(self, goal: Goal) -> List[MicroTask]:
        tasks: List[MicroTask] = []
        previous_id: Optional[str] = None

        for i, sub_task_name in enumerate(goal.sub_tasks):
            task_id = str(uuid.uuid4())
            # تحديد الأداة والنموذج بناءً على اسم المهمة
            assigned_model, assigned_tool = self._assign_resources(sub_task_name, goal)
            # تحديد نمط التنفيذ
            previous_task_name = tasks[-1].name if tasks else None
            mode = self._determine_mode(i, goal, sub_task_name, previous_task_name)
            # التبعيات
            depends = [previous_id] if previous_id and mode == ExecutionMode.SEQUENTIAL else []

            task = MicroTask(
                task_id=task_id,
                name=sub_task_name,
                description=f"تنفيذ: {sub_task_name} — ضمن هدف: {goal.final_objective[:50]}",
                priority=self._assign_priority(i, goal),
                execution_mode=mode,
                depends_on=depends,
                assigned_model=assigned_model,
                assigned_tool=assigned_tool,
                estimated_tokens=self._estimate_tokens(sub_task_name, goal),
                max_retries=3 if goal.complexity != ComplexityLevel.SIMPLE else 1,
                timeout_seconds=self._estimate_timeout(sub_task_name, goal),
                metadata={"goal_intent": goal.intent, "position": i},
            )
            tasks.append(task)
            previous_id = task_id

        return tasks

    def _assign_resources(self, task_name: str, goal: Goal) -> tuple:
        name_lower = task_name.lower()
        model = None
        tool = None

        if "تدريب" in name_lower or "train" in name_lower:
            tool = "training_pipeline"
        elif "تنظيف" in name_lower or "clean" in name_lower:
            tool = "data_cleaner"
        elif "بحث" in name_lower or "search" in name_lower:
            tool = "web_search"
        elif "تقييم" in name_lower or "evaluate" in name_lower:
            tool = "model_evaluator"
        elif "نشر" in name_lower or "deploy" in name_lower:
            tool = "deployment_manager"
        elif "كود" in name_lower or "code" in name_lower:
            model = "qwen2.5-coder-7b"

        if model is None and goal.suitable_models:
            model = goal.suitable_models[0]

        return model, tool

    def _determine_mode(self, index: int, goal: Goal, current_task_name: str, previous_task_name: Optional[str]) -> ExecutionMode:
        # Simple tasks are always sequential
        if goal.complexity == ComplexityLevel.SIMPLE:
            return ExecutionMode.SEQUENTIAL

        # Heuristics for potential parallelism
        # If the task explicitly mentions 'parallel' or 'concurrent'
        if "بالتوازي" in current_task_name or "متزامن" in current_task_name:
            return ExecutionMode.PARALLEL

        # If previous task is a data collection and current is another data collection
        if previous_task_name and ("جمع البيانات" in previous_task_name and "جمع البيانات" in current_task_name):
            return ExecutionMode.PARALLEL

        # If tasks are independent (e.g., analysis of different aspects)
        if goal.intent in [IntentType.ANALYSIS, IntentType.RESEARCH] and goal.complexity != ComplexityLevel.SIMPLE:
            return ExecutionMode.PARALLEL

        # Default to sequential for most cases, especially for complex workflows where order matters
        return ExecutionMode.SEQUENTIAL

    def _assign_priority(self, index: int, goal: Goal) -> TaskPriority:
        if index == 0:
            return TaskPriority.CRITICAL
        if index == 1:
            return TaskPriority.HIGH
        return TaskPriority.MEDIUM

    def _estimate_tokens(self, task_name: str, goal: Goal) -> int:
        base = 500
        if goal.complexity == ComplexityLevel.ENTERPRISE:
            base = 2000
        elif goal.complexity == ComplexityLevel.COMPLEX:
            base = 1000
        elif goal.complexity == ComplexityLevel.MEDIUM:
            base = 700
        return base

    def _estimate_timeout(self, task_name: str, goal: Goal) -> int:
        if "تدريب" in task_name:
            return 3600  # ساعة للتدريب
        if "نشر" in task_name:
            return 300
        return 120  # دقيقتان للمهام العادية

    def get_plan(self, plan_id: str) -> Optional[DecompositionPlan]:
        return self._plans.get(plan_id)


# Singleton
_decomposer: Optional[TaskDecomposer] = None


def get_task_decomposer() -> TaskDecomposer:
    global _decomposer
    if _decomposer is None:
        _decomposer = TaskDecomposer()
    return _decomposer
