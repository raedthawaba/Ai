"""
Autonomous Planning Engine
=========================
محرك التخطيط المستقل والمتقدم.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .goal_manager import Goal
from .task_decomposer import DecompositionPlan, MicroTask, TaskPriority
from .graph_planner import ExecutionGraph
from .plan_validator import PlanValidator, ValidationResult

logger = logging.getLogger(__name__)


class PlanningMode(str, Enum):
    HIERARCHICAL = "hierarchical"  # تخطيط هرمي
    RECURSIVE = "recursive"  # تخطيط تكراري
    LONG_HORIZON = "long_horizon"  # أفق طويل
    AUTONOMOUS = "autonomous"  # مستقل


class PlanQuality(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"


@dataclass
class PlanningMetrics:
    planning_time_ms: float
    iterations: int
    quality_score: float
    complexity: int
    parallelizable: bool
    confidence: float


@dataclass
class AutonomousPlan:
    plan_id: str
    mode: PlanningMode
    root_goal: Goal
    sub_plans: List[DecompositionPlan]
    execution_graph: ExecutionGraph
    validation_result: ValidationResult
    metrics: PlanningMetrics
    metadata: Dict[str, Any] = field(default_factory=dict)


class HierarchicalPlanner:
    """
    مخطط هرمي - يقسم الأهداف الكبيرة إلى مستويات هرمية.
    """

    def __init__(self, max_depth: int = 5) -> None:
        self.max_depth = max_depth

    async def plan(self, goal: Goal) -> List[DecompositionPlan]:
        """التخطيط الهرمي."""
        plans = []
        current_goal = goal
        depth = 0

        while depth < self.max_depth:
            # تفكيك الهدف الحالي
            from .task_decomposer import TaskDecomposer
            decomposer = TaskDecomposer()
            plan = await decomposer.decompose(current_goal)

            plans.append(plan)

            # إذا كان الهدف بسيطاً، توقف
            if len(plan.tasks) <= 3 or not plan.can_parallelize:
                break

            # إنشاء هدف فرعي للمتابعة
            if plan.tasks:
                last_task = plan.tasks[-1]
                current_goal = Goal(
                    goal_id=str(uuid.uuid4()),
                    original_request=f"متابعة: {last_task.name}",
                    final_objective=last_task.description,
                    intent=goal.intent,
                    complexity=goal.complexity,
                    domain=goal.domain,
                    sub_tasks=[],
                    required_tools=goal.required_tools,
                    suitable_models=goal.suitable_models,
                    confidence=goal.confidence * 0.9,
                )

            depth += 1

        logger.info("hierarchical_planner: created %d plans at depth %d", len(plans), depth)
        return plans


class RecursivePlanner:
    """
    مخطط تكراري - يحل المشكلة بتقسيمها إلى مشاكل أصغر متشابهة.
    """

    def __init__(self, base_case_threshold: int = 3) -> None:
        self.base_case_threshold = base_case_threshold
        self._recursion_depth = 0

    async def plan(self, goal: Goal) -> DecompositionPlan:
        """التخطيط التكراري."""
        self._recursion_depth = 0
        return await self._recursive_decompose(goal)

    async def _recursive_decompose(
        self, goal: Goal, depth: int = 0
    ) -> DecompositionPlan:
        """التحليل التكراري."""
        self._recursion_depth = max(self._recursion_depth, depth)

        # حالة القاعدة
        if len(goal.sub_tasks) <= self.base_case_threshold:
            return await self._create_leaf_plan(goal, depth)

        # التقسيم التكراري
        mid = len(goal.sub_tasks) // 2
        sub_goals = [
            self._split_goal(goal, goal.sub_tasks[:mid], depth + 1, "left"),
            self._split_goal(goal, goal.sub_tasks[mid:], depth + 1, "right"),
        ]

        # حل المشاكل الفرعية
        sub_plans = []
        for sub_goal in sub_goals:
            sub_plan = await self._recursive_decompose(sub_goal, depth + 1)
            sub_plans.append(sub_plan)

        # دمج الخطط الفرعية
        return self._merge_plans(goal, sub_plans)

    def _split_goal(self, goal: Goal, tasks: List[str], depth: int, suffix: str) -> Goal:
        """تقسيم الهدف."""
        return Goal(
            goal_id=f"{goal.goal_id}-{suffix}",
            original_request=f"{goal.original_request} [{suffix}]",
            final_objective=goal.final_objective,
            intent=goal.intent,
            complexity=goal.complexity,
            domain=goal.domain,
            sub_tasks=tasks,
            required_tools=goal.required_tools,
            suitable_models=goal.suitable_models,
            confidence=goal.confidence * 0.95,
        )

    async def _create_leaf_plan(self, goal: Goal, depth: int) -> DecompositionPlan:
        """إنشاء خطة الورقة."""
        from .task_decomposer import TaskDecomposer, ExecutionMode

        tasks = [
            MicroTask(
                task_id=str(uuid.uuid4()),
                name=task_name,
                description=f"{task_name} (عمق {depth})",
                priority=TaskPriority.MEDIUM,
                execution_mode=ExecutionMode.SEQUENTIAL,
                depends_on=[],
                assigned_model=None,
                assigned_tool=None,
                estimated_tokens=500,
                max_retries=2,
                timeout_seconds=120,
            )
            for task_name in goal.sub_tasks
        ]

        return DecompositionPlan(
            plan_id=str(uuid.uuid4()),
            goal_id=goal.goal_id,
            tasks=tasks,
            total_estimated_tokens=sum(t.estimated_tokens for t in tasks),
            estimated_duration_seconds=len(tasks) * 2,
            can_parallelize=False,
            metadata={"depth": depth, "type": "leaf"},
        )

    def _merge_plans(
        self, goal: Goal, sub_plans: List[DecompositionPlan]
    ) -> DecompositionPlan:
        """دمج الخطط الفرعية."""
        all_tasks = []
        for plan in sub_plans:
            all_tasks.extend(plan.tasks)

        return DecompositionPlan(
            plan_id=str(uuid.uuid4()),
            goal_id=goal.goal_id,
            tasks=all_tasks,
            total_estimated_tokens=sum(p.total_estimated_tokens for p in sub_plans),
            estimated_duration_seconds=sum(p.estimated_duration_seconds for p in sub_plans),
            can_parallelize=True,
            metadata={"type": "merged", "sub_plans": len(sub_plans)},
        )


class LongHorizonPlanner:
    """
    مخطط الأفق الطويل - للتخطيط على عدة مراحل زمنية.
    """

    def __init__(self, horizon_steps: int = 10) -> None:
        self.horizon_steps = horizon_steps

    async def plan(self, goal: Goal) -> List[DecompositionPlan]:
        """التخطيط على أفق طويل."""
        plans = []
        remaining_objective = goal.final_objective
        step = 0

        while step < self.horizon_steps and remaining_objective:
            # إنشاء هدف لهذه الخطوة
            step_goal = Goal(
                goal_id=f"{goal.goal_id}-step-{step}",
                original_request=f"الخطوة {step + 1}: {remaining_objective[:100]}",
                final_objective=remaining_objective,
                intent=goal.intent,
                complexity=goal.complexity,
                domain=goal.domain,
                sub_tasks=goal.sub_tasks[step * 3 : (step + 1) * 3] if goal.sub_tasks else [],
                required_tools=goal.required_tools,
                suitable_models=goal.suitable_models,
                confidence=goal.confidence * (0.9 ** step),
            )

            # تفكيك الخطوة
            from .task_decomposer import TaskDecomposer
            decomposer = TaskDecomposer()
            plan = await decomposer.decompose(step_goal)
            plan.metadata["horizon_step"] = step
            plan.metadata["total_horizon"] = self.horizon_steps

            plans.append(plan)

            # التحديث للمرحلة التالية
            remaining_objective = remaining_objective[len(step_goal.original_request) :]
            step += 1

            if not step_goal.sub_tasks:
                break

        logger.info("long_horizon_planner: created %d step plans", len(plans))
        return plans


class SelfImprovingPlanner:
    """
    مخطط متحسن ذاتياً - يتعلم من خططه السابقة.
    """

    def __init__(self) -> None:
        self._plan_history: List[Dict[str, Any]] = []
        self._success_patterns: Dict[str, int] = {}
        self._failure_patterns: Dict[str, int] = {}

    async def plan(
        self, goal: Goal, previous_results: Optional[List[Dict]] = None
    ) -> Tuple[DecompositionPlan, Dict[str, Any]]:
        """التخطيط مع التحسين الذاتي."""
        start_time = time.time()

        # استخدام الأنماط الناجحة السابقة
        patterns = self._get_successful_patterns(goal)
        
        # التخطيط الأساسي
        from .task_decomposer import TaskDecomposer
        decomposer = TaskDecomposer()
        plan = await decomposer.decompose(goal)

        # تحسين الخطة بناءً على الأنماط
        if patterns:
            plan = self._apply_patterns(plan, patterns)

        # حساب المقاييس
        planning_time = (time.time() - start_time) * 1000
        metrics = {
            "planning_time_ms": planning_time,
            "patterns_used": len(patterns),
            "quality_improvement": self._calculate_improvement(plan),
        }

        # تسجيل الخطة
        self._record_plan(goal, plan, metrics)

        return plan, metrics

    def _get_successful_patterns(self, goal: Goal) -> List[str]:
        """الحصول على الأنماط الناجحة."""
        patterns = []
        for pattern, count in self._success_patterns.items():
            if count >= 2:
                patterns.append(pattern)
        return patterns[:3]

    def _apply_patterns(
        self, plan: DecompositionPlan, patterns: List[str]
    ) -> DecompositionPlan:
        """تطبيق الأنماط على الخطة."""
        # ترتيب الأولويات حسب الأنماط
        for pattern in patterns:
            if "parallel" in pattern.lower():
                # تحديث أنماط التنفيذ
                for task in plan.tasks:
                    if not task.depends_on:
                        task.execution_mode = "parallel"

        return plan

    def _calculate_improvement(self, plan: DecompositionPlan) -> float:
        """حساب التحسن."""
        base_quality = 0.7
        parallel_bonus = 0.1 if plan.can_parallelize else 0
        complexity_penalty = min(0.1, len(plan.tasks) * 0.01)
        return base_quality + parallel_bonus - complexity_penalty

    def _record_plan(
        self, goal: Goal, plan: DecompositionPlan, metrics: Dict[str, Any]
    ) -> None:
        """تسجيل الخطة للتعلم."""
        record = {
            "goal_id": goal.goal_id,
            "intent": goal.intent.value,
            "complexity": goal.complexity.value,
            "task_count": len(plan.tasks),
            "can_parallelize": plan.can_parallelize,
            "metrics": metrics,
            "timestamp": time.time(),
        }
        self._plan_history.append(record)

        # الاحتفاظ بآخر 1000 سجل
        if len(self._plan_history) > 1000:
            self._plan_history = self._plan_history[-1000:]

    def record_outcome(self, plan_id: str, success: bool) -> None:
        """تسجيل نتيجة الخطة."""
        for record in reversed(self._plan_history):
            if record.get("goal_id") == plan_id:
                pattern = f"{record['intent']}_{record['complexity']}"
                if success:
                    self._success_patterns[pattern] = self._success_patterns.get(pattern, 0) + 1
                else:
                    self._failure_patterns[pattern] = self._failure_patterns.get(pattern, 0) + 1
                break

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على الإحصائيات."""
        return {
            "total_plans": len(self._plan_history),
            "successful_patterns": dict(self._success_patterns),
            "failure_patterns": dict(self._failure_patterns),
            "best_patterns": sorted(
                self._success_patterns.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }


class AutonomousPlanningEngine:
    """
    محرك التخطيط المستقل - يجمع جميع استراتيجيات التخطيط.
    """

    def __init__(self) -> None:
        self.hierarchical = HierarchicalPlanner()
        self.recursive = RecursivePlanner()
        self.long_horizon = LongHorizonPlanner()
        self.self_improving = SelfImprovingPlanner()
        self.validator = PlanValidator()

    async def plan(
        self,
        goal: Goal,
        mode: PlanningMode = PlanningMode.AUTONOMOUS,
        validate: bool = True,
    ) -> AutonomousPlan:
        """التخطيط الكامل."""
        start_time = time.time()

        # التخطيط بناءً على الوضع
        if mode == PlanningMode.HIERARCHICAL:
            sub_plans = await self.hierarchical.plan(goal)
            main_plan = sub_plans[0] if sub_plans else None
        elif mode == PlanningMode.RECURSIVE:
            main_plan = await self.recursive.plan(goal)
            sub_plans = [main_plan]
        elif mode == PlanningMode.LONG_HORIZON:
            sub_plans = await self.long_horizon.plan(goal)
            main_plan = sub_plans[0] if sub_plans else None
        else:  # AUTONOMOUS
            # اختيار الوضع الأنسب تلقائياً
            if len(goal.sub_tasks) > 10:
                sub_plans = await self.hierarchical.plan(goal)
            elif len(goal.sub_tasks) > 5:
                main_plan = await self.recursive.plan(goal)
                sub_plans = [main_plan]
            else:
                from .task_decomposer import TaskDecomposer
                decomposer = TaskDecomposer()
                main_plan = await decomposer.decompose(goal)
                sub_plans = [main_plan]

        # بناء الرسم البياني
        from .graph_planner import GraphPlanner
        planner = GraphPlanner()
        execution_graph = await planner.build_graph(main_plan)

        # التحقق
        validation_result = None
        if validate:
            validation_result = await self.validator.validate(main_plan, execution_graph)

        # حساب المقاييس
        planning_time = (time.time() - start_time) * 1000
        quality_score = validation_result.score if validation_result else 0.8
        confidence = goal.confidence * quality_score

        metrics = PlanningMetrics(
            planning_time_ms=planning_time,
            iterations=1,
            quality_score=quality_score,
            complexity=len(main_plan.tasks),
            parallelizable=main_plan.can_parallelize,
            confidence=confidence,
        )

        return AutonomousPlan(
            plan_id=str(uuid.uuid4()),
            mode=mode,
            root_goal=goal,
            sub_plans=sub_plans,
            execution_graph=execution_graph,
            validation_result=validation_result,
            metrics=metrics,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات المحرك."""
        return {
            "self_improving_stats": self.self_improving.get_statistics(),
            "recursive_depth": self.recursive._recursion_depth,
        }


# Singleton
_engine: Optional[AutonomousPlanningEngine] = None


def get_autonomous_planning_engine() -> AutonomousPlanningEngine:
    global _engine
    if _engine is None:
        _engine = AutonomousPlanningEngine()
    return _engine
