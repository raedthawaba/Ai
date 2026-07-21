"""
Plan Validator + Adaptive Replanning
====================================
يتحقق من صحة الخطة قبل التنفيذ ويقوم بإصلاحها ديناميكياً.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .graph_planner import ExecutionGraph, GraphNode, NodeType
from .task_decomposer import DecompositionPlan, MicroTask

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    PARTIAL = "partial"
    NEEDS_REPAIR = "needs_repair"


class ValidationErrorType(str, Enum):
    CIRCULAR_DEPENDENCY = "circular_dependency"
    MISSING_DEPENDENCY = "missing_dependency"
    RESOURCE_OVERFLOW = "resource_overflow"
    TIMEOUT_EXCEEDED = "timeout_exceeded"
    UNREACHABLE_NODE = "unreachable_node"
    INVALID_SEQUENCE = "invalid_sequence"


@dataclass
class ValidationError:
    error_id: str
    error_type: ValidationErrorType
    node_ids: List[str]
    description: str
    severity: str  # critical, high, medium, low
    fix_suggestion: str


@dataclass
class ValidationResult:
    plan_id: str
    status: ValidationStatus
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str]
    score: float  # 0-1
    validated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlanValidator:
    """
    يتحقق من صحة خطة التنفيذ.
    
    التحقق يشمل:
    - التبعيات الدائرية (Circular Dependencies)
    - التبعيات المفقودة (Missing Dependencies)
    - تجاوز الموارد (Resource Overflow)
    - تجاوز الوقت (Timeout)
    - العقد غير القابلة للوصول (Unreachable Nodes)
    """

    def __init__(self, max_tokens: int = 100000, max_duration_seconds: float = 3600) -> None:
        self.max_tokens = max_tokens
        self.max_duration_seconds = max_duration_seconds
        self._validation_history: List[ValidationResult] = []

    async def validate(self, plan: DecompositionPlan, graph: ExecutionGraph) -> ValidationResult:
        """التحقق الكامل من الخطة."""
        plan_id = plan.plan_id
        errors: List[ValidationError] = []
        warnings: List[str] = []

        # 1. التحقق من التبعيات الدائرية
        circular_errors = self._check_circular_dependencies(graph)
        errors.extend(circular_errors)

        # 2. التحقق من التبعيات المفقودة
        missing_errors = self._check_missing_dependencies(graph, plan)
        errors.extend(missing_errors)

        # 3. التحقق من الموارد
        resource_errors, resource_warnings = self._check_resources(graph, plan)
        errors.extend(resource_errors)
        warnings.extend(resource_warnings)

        # 4. التحقق من العقد غير القابلة للوصول
        unreachable_errors = self._check_unreachable_nodes(graph)
        errors.extend(unreachable_errors)

        # 5. التحقق من التسلسل الزمني
        sequence_warnings = self._check_sequence_timing(graph, plan)
        warnings.extend(sequence_warnings)

        # حساب النتيجة
        status = self._determine_status(errors)
        score = self._calculate_score(errors, warnings, len(graph.nodes))

        result = ValidationResult(
            plan_id=plan_id,
            status=status,
            is_valid=status == ValidationStatus.VALID,
            errors=errors,
            warnings=warnings,
            score=score,
            validated_at=time.time(),
            metadata={
                "total_nodes": len(graph.nodes),
                "total_errors": len(errors),
                "total_warnings": len(warnings),
            },
        )

        self._validation_history.append(result)
        logger.info(
            "plan_validator: plan=%s status=%s errors=%d score=%.2f",
            plan_id, status.value, len(errors), score
        )

        return result

    def _check_circular_dependencies(self, graph: ExecutionGraph) -> List[ValidationError]:
        """التحقق من التبعيات الدائرية باستخدام DFS."""
        errors: List[ValidationError] = []
        visited: set = set()
        rec_stack: set = set()

        def dfs(node_id: str, path: List[str]) -> Optional[List[str]]:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for successor in graph.get_successors(node_id):
                if successor not in visited:
                    cycle = dfs(successor, path.copy())
                    if cycle:
                        return cycle
                elif successor in rec_stack:
                    # وجدنا دورة
                    cycle_start = path.index(successor)
                    return path[cycle_start:] + [successor]

            rec_stack.remove(node_id)
            return None

        for node_id in graph.nodes:
            if node_id not in visited:
                cycle = dfs(node_id, [])
                if cycle:
                    errors.append(ValidationError(
                        error_id=str(uuid.uuid4()),
                        error_type=ValidationErrorType.CIRCULAR_DEPENDENCY,
                        node_ids=cycle,
                        description=f"دورة في التبعيات: {' -> '.join(cycle[:5])}...",
                        severity="critical",
                        fix_suggestion="إعادة ترتيب المهام لإزالة الدورة",
                    ))

        return errors

    def _check_missing_dependencies(self, graph: ExecutionGraph, plan: DecompositionPlan) -> List[ValidationError]:
        """التحقق من التبعيات المفقودة."""
        errors: List[ValidationError] = []
        task_ids = {t.task_id for t in plan.tasks}

        for task in plan.tasks:
            for dep_id in task.depends_on:
                if dep_id not in task_ids:
                    errors.append(ValidationError(
                        error_id=str(uuid.uuid4()),
                        error_type=ValidationErrorType.MISSING_DEPENDENCY,
                        node_ids=[task.task_id],
                        description=f"المهمة {task.name} تعتمد على {dep_id} غير موجود",
                        severity="high",
                        fix_suggestion=f"إزالة تبعية {dep_id} أو إضافة المهمة المفقودة",
                    ))

        return errors

    def _check_resources(
        self, graph: ExecutionGraph, plan: DecompositionPlan
    ) -> Tuple[List[ValidationError], List[str]]:
        """التحقق من الموارد."""
        errors: List[ValidationError] = []
        warnings: List[str] = []

        total_tokens = plan.total_estimated_tokens
        if total_tokens > self.max_tokens:
            errors.append(ValidationError(
                error_id=str(uuid.uuid4()),
                error_type=ValidationErrorType.RESOURCE_OVERFLOW,
                node_ids=list(graph.nodes.keys()),
                description=f"تجاوز عدد الرموز: {total_tokens} > {self.max_tokens}",
                severity="critical",
                fix_suggestion="تقسيم الخطة إلى مراحل متعددة",
            ))

        if plan.estimated_duration_seconds > self.max_duration_seconds:
            warnings.append(
                f"تجاوز الوقت المتوقع: {plan.estimated_duration_seconds:.0f}s > {self.max_duration_seconds:.0f}s"
            )

        return errors, warnings

    def _check_unreachable_nodes(self, graph: ExecutionGraph) -> List[ValidationError]:
        """التحقق من العقد غير القابلة للوصول."""
        errors: List[ValidationError] = []

        # العقد التي يمكن الوصول إليها من نقاط الدخول
        reachable: set = set()
        queue = list(graph.entry_nodes)

        while queue:
            node_id = queue.pop(0)
            if node_id not in reachable:
                reachable.add(node_id)
                queue.extend(graph.get_successors(node_id))

        # العقد التي لا يمكن الوصول إليها
        unreachable = set(graph.nodes.keys()) - reachable
        if unreachable:
            errors.append(ValidationError(
                error_id=str(uuid.uuid4()),
                error_type=ValidationErrorType.UNREACHABLE_NODE,
                node_ids=list(unreachable),
                description=f"عقد غير قابلة للوصول: {len(unreachable)} من {len(graph.nodes)}",
                severity="medium",
                fix_suggestion="إعادة ربط العقد المعزولة أو إزالتها",
            ))

        return errors

    def _check_sequence_timing(self, graph: ExecutionGraph, plan: DecompositionPlan) -> List[str]:
        """التحقق من التسلسل الزمني."""
        warnings: List[str] = []

        for task in plan.tasks:
            if task.timeout_seconds > 1800:  # أكثر من 30 دقيقة
                warnings.append(
                    f"المهمة '{task.name}' لها timeout طويل: {task.timeout_seconds}s"
                )

        return warnings

    def _determine_status(self, errors: List[ValidationError]) -> ValidationStatus:
        """تحديد حالة الخطة."""
        if not errors:
            return ValidationStatus.VALID

        critical_count = sum(1 for e in errors if e.severity == "critical")
        high_count = sum(1 for e in errors if e.severity == "high")

        if critical_count > 0:
            return ValidationStatus.INVALID
        elif high_count > 0:
            return ValidationStatus.NEEDS_REPAIR
        else:
            return ValidationStatus.PARTIAL

    def _calculate_score(
        self, errors: List[ValidationError], warnings: List[str], total_nodes: int
    ) -> float:
        """حساب درجة صحة الخطة."""
        if total_nodes == 0:
            return 0.0

        # خصم حسب الأخطاء
        error_penalty = len(errors) * 0.1
        warning_penalty = len(warnings) * 0.02

        score = max(0.0, 1.0 - error_penalty - warning_penalty)
        return round(score, 3)

    def get_validation_history(self, limit: int = 10) -> List[ValidationResult]:
        """الحصول على سجل التحقق."""
        return self._validation_history[-limit:]


class AdaptiveReplanner:
    """
    يقوم بإصلاح الخطة ديناميكياً عند الفشل.
    
    الاستراتيجيات:
    - إعادة ترتيب المهام
    - إضافة/إزالة التبعيات
    - تقسيم المهام الكبيرة
    - تغيير ترتيب التنفيذ
    """

    def __init__(self) -> None:
        self._repair_history: List[Dict[str, Any]] = []

    async def repair(
        self, plan: DecompositionPlan, graph: ExecutionGraph, errors: List[ValidationError]
    ) -> Tuple[DecompositionPlan, ExecutionGraph, List[str]]:
        """إصلاح الخطة بناءً على الأخطاء."""
        repairs: List[str] = []
        modified_tasks = list(plan.tasks)
        modified_graph = graph

        for error in errors:
            if error.error_type == ValidationErrorType.CIRCULAR_DEPENDENCY:
                # إزالة الدورة
                modified_tasks = self._remove_cycle(modified_tasks, error.node_ids)
                repairs.append(f"تم إزالة دورة في: {error.node_ids[:3]}")

            elif error.error_type == ValidationErrorType.MISSING_DEPENDENCY:
                # إزالة التبعية المفقودة
                modified_tasks = self._fix_missing_dependency(modified_tasks, error)
                repairs.append(f"تم إصلاح تبعية مفقودة: {error.node_ids}")

            elif error.error_type == ValidationErrorType.RESOURCE_OVERFLOW:
                # تقسيم المهام الكبيرة
                modified_tasks = self._split_large_tasks(modified_tasks)
                repairs.append("تم تقسيم المهام الكبيرة")

            elif error.error_type == ValidationErrorType.UNREACHABLE_NODE:
                # ربط العقد المعزولة
                modified_tasks = self._connect_isolated_nodes(modified_tasks, error.node_ids)
                repairs.append(f"تم ربط {len(error.node_ids)} عقدة معزولة")

        # إعادة بناء الخطة
        new_plan = DecompositionPlan(
            plan_id=str(uuid.uuid4()),
            goal_id=plan.goal_id,
            tasks=modified_tasks,
            total_estimated_tokens=sum(t.estimated_tokens for t in modified_tasks),
            estimated_duration_seconds=plan.estimated_duration_seconds,
            can_parallelize=plan.can_parallelize,
            metadata={**plan.metadata, "repaired_from": plan.plan_id},
        )

        # إعادة بناء الرسم البياني
        from .graph_planner import GraphPlanner
        planner = GraphPlanner()
        new_graph = await planner.build_graph(new_plan)

        self._repair_history.append({
            "original_plan_id": plan.plan_id,
            "new_plan_id": new_plan.plan_id,
            "repairs": repairs,
            "errors_count": len(errors),
            "timestamp": time.time(),
        })

        logger.info(
            "adaptive_replanner: repaired plan %s -> %s (%d repairs)",
            plan.plan_id, new_plan.plan_id, len(repairs)
        )

        return new_plan, new_graph, repairs

    def _remove_cycle(self, tasks: List[MicroTask], cycle_nodes: List[str]) -> List[MicroTask]:
        """إزالة الدورة من المهام."""
        cycle_set = set(cycle_nodes)
        fixed_tasks = []

        for task in tasks:
            if task.task_id not in cycle_set:
                # إزالة التبعيات التي تسبب الدورة
                new_depends = [d for d in task.depends_on if d not in cycle_set]
                task.depends_on = new_depends
                fixed_tasks.append(task)

        return fixed_tasks

    def _fix_missing_dependency(
        self, tasks: List[MicroTask], error: ValidationError
    ) -> List[MicroTask]:
        """إصلاح التبعية المفقودة."""
        fixed_tasks = []

        for task in tasks:
            if task.task_id in error.node_ids:
                # إزالة التبعية المفقودة
                task.depends_on = [d for d in task.depends_on if d not in error.node_ids]
            fixed_tasks.append(task)

        return fixed_tasks

    def _split_large_tasks(self, tasks: List[MicroTask]) -> List[MicroTask]:
        """تقسيم المهام الكبيرة."""
        new_tasks = []

        for task in tasks:
            if task.estimated_tokens > 5000:
                # تقسيم إلى مهمتين
                mid = len(task.depends_on) // 2
                task1 = MicroTask(
                    task_id=str(uuid.uuid4()),
                    name=f"{task.name} (جزء 1)",
                    description=task.description,
                    priority=task.priority,
                    execution_mode=task.execution_mode,
                    depends_on=task.depends_on,
                    assigned_model=task.assigned_model,
                    assigned_tool=task.assigned_tool,
                    estimated_tokens=task.estimated_tokens // 2,
                    max_retries=task.max_retries,
                    timeout_seconds=task.timeout_seconds // 2,
                    metadata={**task.metadata, "split_from": task.task_id},
                )
                task2 = MicroTask(
                    task_id=str(uuid.uuid4()),
                    name=f"{task.name} (جزء 2)",
                    description=task.description,
                    priority=task.priority,
                    execution_mode=task.execution_mode,
                    depends_on=[task1.task_id],
                    assigned_model=task.assigned_model,
                    assigned_tool=task.assigned_tool,
                    estimated_tokens=task.estimated_tokens // 2,
                    max_retries=task.max_retries,
                    timeout_seconds=task.timeout_seconds // 2,
                    metadata={**task.metadata, "split_from": task.task_id},
                )
                new_tasks.extend([task1, task2])
            else:
                new_tasks.append(task)

        return new_tasks

    def _connect_isolated_nodes(
        self, tasks: List[MicroTask], isolated_ids: List[str]
    ) -> List[MicroTask]:
        """ربط العقد المعزولة."""
        connected_tasks = list(tasks)

        if tasks and isolated_ids:
            # ربط أول عقدة معزولة بآخر مهمة
            last_task = tasks[-1]
            for task in connected_tasks:
                if task.task_id in isolated_ids:
                    if task.task_id not in task.depends_on:
                        task.depends_on.append(last_task.task_id)

        return connected_tasks

    def get_repair_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """الحصول على سجل الإصلاحات."""
        return self._repair_history[-limit:]


class StrategySelector:
    """
    يختار استراتيجية التنفيذ الأنسب بناءً على سياق الخطة.
    """

    STRATEGY_PATTERNS = {
        "parallel_first": ["parallel", "concurrent", "متزامن"],
        "sequential": ["sequential", "تسلسل", "خطوة بخطوة"],
        "adaptive": ["complex", "enterprise"],
        "minimal": ["simple", "minimal"],
    }

    def select_strategy(self, plan: DecompositionPlan, graph: ExecutionGraph) -> str:
        """اختيار الاستراتيجية الأنسب."""
        # فحص النمط في اسم الهدف
        goal_lower = plan.metadata.get("intent", "").lower()

        for strategy, patterns in self.STRATEGY_PATTERNS.items():
            if any(p in goal_lower for p in patterns):
                return strategy

        # اختيار افتراضي بناءً على التعقيد
        if plan.can_parallelize and len(plan.tasks) > 5:
            return "parallel_first"
        elif len(plan.tasks) <= 3:
            return "sequential"
        else:
            return "adaptive"

    def get_strategy_config(self, strategy: str) -> Dict[str, Any]:
        """الحصول على إعدادات الاستراتيجية."""
        configs = {
            "parallel_first": {
                "batch_size": 5,
                "parallel_limit": 3,
                "timeout_multiplier": 1.5,
            },
            "sequential": {
                "batch_size": 1,
                "parallel_limit": 1,
                "timeout_multiplier": 1.0,
            },
            "adaptive": {
                "batch_size": 3,
                "parallel_limit": 2,
                "timeout_multiplier": 1.2,
            },
            "minimal": {
                "batch_size": 1,
                "parallel_limit": 1,
                "timeout_multiplier": 0.8,
            },
        }
        return configs.get(strategy, configs["adaptive"])


# Singleton instances
_validator: Optional[PlanValidator] = None
_replanner: Optional[AdaptiveReplanner] = None
_selector: Optional[StrategySelector] = None


def get_plan_validator() -> PlanValidator:
    global _validator
    if _validator is None:
        _validator = PlanValidator()
    return _validator


def get_adaptive_replanner() -> AdaptiveReplanner:
    global _replanner
    if _replanner is None:
        _replanner = AdaptiveReplanner()
    return _replanner


def get_strategy_selector() -> StrategySelector:
    global _selector
    if _selector is None:
        _selector = StrategySelector()
    return _selector
