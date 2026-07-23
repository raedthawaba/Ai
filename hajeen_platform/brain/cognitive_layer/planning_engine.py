"""
Planning Engine — محرك التخطيط
================================
جزء من HajeenBrainV3 Pipeline الموحّد.

يقوم بـ:
1. تحويل الأهداف إلى خطط قابلة للتنفيذ
2. بناء DAG (Directed Acyclic Graph) للمهام
3. تحديد التبعيات بين المهام
4. تحسين الخطة بناءً على الموارد المتاحة
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    CRITICAL = "critical"      # يجب تنفيذه فوراً
    HIGH = "high"              # أولوية عالية
    MEDIUM = "medium"          # أولوية متوسطة
    LOW = "low"                # أولوية منخفضة
    BACKGROUND = "background"  # خلفية


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"            # جميع التبعيات مكتملة
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"        # تبعية فاشلة


@dataclass
class Task:
    """مهمة واحدة في الخطة."""
    id: str
    name: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # IDs of tasks this depends on
    estimated_duration_ms: int = 1000
    required_resources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class Plan:
    """خطة كاملة مكونة من مهام مترابطة."""
    id: str
    goal: str
    tasks: Dict[str, Task]
    execution_order: List[str]  # Ordered task IDs
    parallel_groups: List[List[str]]  # Tasks that can run in parallel
    estimated_total_duration_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanningResult:
    """نتيجة عملية التخطيط."""
    plan: Plan
    confidence: float
    alternatives: List[Plan]
    planning_time_ms: float


class PlanningEngine:
    """
    محرك التخطيط — يحول الأهداف إلى خطط قابلة للتنفيذ.

    يستخدم ضمن HajeenBrainV3 Pipeline:
      Policy → Intent → Context → Reasoning → [Planning] → Decision → Execute
    """

    def __init__(self, llm_manager=None):
        self.llm_manager = llm_manager
        logger.info("PlanningEngine initialized")

    # ── Core Methods ──────────────────────────────────────────────────────

    async def plan(
        self,
        goal: str,
        context: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        available_resources: Optional[List[str]] = None,
    ) -> PlanningResult:
        """
        التخطيط الرئيسي — يحول الهدف إلى خطة.

        Args:
            goal: الهدف المراد تحقيقه
            context: سياق إضافي
            constraints: قيود (مثل وقت، موارد)
            available_resources: الموارد المتاحة
        """
        import time
        start = time.perf_counter()

        logger.info("Planning: goal=%s", goal[:50])

        # 1. Decompose goal into tasks
        tasks = await self._decompose_goal(goal, context)

        # 2. Identify dependencies
        tasks = self._identify_dependencies(tasks)

        # 3. Assign priorities
        tasks = self._assign_priorities(tasks, goal)

        # 4. Build execution order (topological sort)
        execution_order = self._topological_sort(tasks)

        # 5. Identify parallel groups
        parallel_groups = self._identify_parallel_groups(tasks, execution_order)

        # 6. Calculate total duration
        total_duration = self._calculate_duration(tasks, execution_order)

        # 7. Apply constraints
        if constraints:
            tasks = self._apply_constraints(tasks, constraints)

        # 8. Generate alternatives
        alternatives = await self._generate_alternatives(goal, tasks, context)

        elapsed = (time.perf_counter() - start) * 1000

        plan = Plan(
            id=f"plan_{hash(goal) % 100000:05d}",
            goal=goal,
            tasks=tasks,
            execution_order=execution_order,
            parallel_groups=parallel_groups,
            estimated_total_duration_ms=total_duration,
            metadata={
                "num_tasks": len(tasks),
                "num_parallel_groups": len(parallel_groups),
                "constraints": constraints or [],
            }
        )

        confidence = self._calculate_plan_confidence(plan)

        return PlanningResult(
            plan=plan,
            confidence=confidence,
            alternatives=alternatives[:3],  # Keep top 3 alternatives
            planning_time_ms=elapsed,
        )

    # ── Task Decomposition ────────────────────────────────────────────────

    async def _decompose_goal(
        self,
        goal: str,
        context: Optional[str],
    ) -> Dict[str, Task]:
        """تفكيك الهدف إلى مهام."""
        tasks = {}

        if self.llm_manager:
            try:
                prompt = f"""قسّم الهدف التالي إلى مهام صغيرة قابلة للتنفيذ:

الهدف: {goal}

{context or ""}

أخرج النتيجة كـ JSON list:
[
  {{"name": "...", "description": "...", "priority": "high|medium|low"}},
  ...
]"""
                response = await self.llm_manager.agenerate(prompt, temperature=0.3)
                parsed = self._parse_task_list(response)
                for i, t in enumerate(parsed):
                    task_id = f"task_{i:03d}"
                    tasks[task_id] = Task(
                        id=task_id,
                        name=t.get("name", f"Task {i}"),
                        description=t.get("description", ""),
                        priority=TaskPriority(t.get("priority", "medium")),
                    )
            except Exception as exc:
                logger.warning("LLM decomposition failed: %s, using fallback", exc)
                tasks = self._fallback_decomposition(goal)
        else:
            tasks = self._fallback_decomposition(goal)

        return tasks

    def _fallback_decomposition(self, goal: str) -> Dict[str, Task]:
        """تفكيك افتراضي عند فشل LLM."""
        return {
            "task_000": Task(
                id="task_000",
                name="فهم الهدف",
                description=f"تحليل وفهم الهدف: {goal[:100]}",
                priority=TaskPriority.HIGH,
            ),
            "task_001": Task(
                id="task_001",
                name="جمع المعلومات",
                description="جمع المعلومات والسياق اللازم",
                priority=TaskPriority.HIGH,
                dependencies=["task_000"],
            ),
            "task_002": Task(
                id="task_002",
                name="تحليل الخيارات",
                description="تحليل الخيارات المتاحة",
                priority=TaskPriority.MEDIUM,
                dependencies=["task_001"],
            ),
            "task_003": Task(
                id="task_003",
                name="تنفيذ الحل",
                description="تنفيذ الحل الأمثل",
                priority=TaskPriority.HIGH,
                dependencies=["task_002"],
            ),
            "task_004": Task(
                id="task_004",
                name="التحقق من النتيجة",
                description="التحقق من صحة النتيجة",
                priority=TaskPriority.MEDIUM,
                dependencies=["task_003"],
            ),
        }

    def _parse_task_list(self, text: str) -> List[Dict[str, str]]:
        """تحليل قائمة المهام من نص LLM."""
        try:
            # Try to find JSON in text
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                return json.loads(text[start:end+1])
        except:
            pass

        # Fallback: parse line by line
        tasks = []
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith("[") and not line.startswith("]"):
                tasks.append({"name": line, "description": line, "priority": "medium"})
        return tasks

    # ── Dependency Management ───────────────────────────────────────────

    def _identify_dependencies(self, tasks: Dict[str, Task]) -> Dict[str, Task]:
        """تحديد التبعيات بين المهام."""
        # Simple heuristic: earlier tasks depend on later ones
        task_ids = list(tasks.keys())
        for i, task_id in enumerate(task_ids):
            if i > 0 and not tasks[task_id].dependencies:
                # Task depends on previous task
                tasks[task_id].dependencies = [task_ids[i-1]]
        return tasks

    def _topological_sort(self, tasks: Dict[str, Task]) -> List[str]:
        """ترتيب المهام طوبولوجياً (حسب التبعيات)."""
        visited = set()
        result = []

        def visit(task_id: str):
            if task_id in visited:
                return
            visited.add(task_id)
            for dep_id in tasks[task_id].dependencies:
                if dep_id in tasks:
                    visit(dep_id)
            result.append(task_id)

        for task_id in tasks:
            visit(task_id)

        return result

    def _identify_parallel_groups(
        self,
        tasks: Dict[str, Task],
        execution_order: List[str],
    ) -> List[List[str]]:
        """تحديد مجموعات المهام التي يمكن تنفيذها بالتوازي."""
        groups = []
        current_group = []
        completed = set()

        for task_id in execution_order:
            task = tasks[task_id]
            # Check if all dependencies are completed
            if all(dep_id in completed for dep_id in task.dependencies):
                current_group.append(task_id)
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [task_id]
            completed.add(task_id)

        if current_group:
            groups.append(current_group)

        return groups

    def _calculate_duration(
        self,
        tasks: Dict[str, Task],
        execution_order: List[str],
    ) -> int:
        """حساب المدة الإجمالية التقديرية."""
        return sum(tasks[tid].estimated_duration_ms for tid in execution_order)

    def _assign_priorities(
        self,
        tasks: Dict[str, Task],
        goal: str,
    ) -> Dict[str, Task]:
        """تعيين الأولويات بناءً على الهدف."""
        goal_lower = goal.lower()
        for task in tasks.values():
            if any(w in task.name.lower() for w in ["أمان", "security", "safety", "أخلاق", "ethics"]):
                task.priority = TaskPriority.CRITICAL
            elif any(w in task.name.lower() for w in ["فهم", "understand", "تحليل", "analyze"]):
                task.priority = TaskPriority.HIGH
        return tasks

    def _apply_constraints(
        self,
        tasks: Dict[str, Task],
        constraints: List[str],
    ) -> Dict[str, Task]:
        """تطبيق القيود على المهام."""
        for constraint in constraints:
            if "time" in constraint.lower() or "وقت" in constraint:
                # Reduce estimated durations
                for task in tasks.values():
                    task.estimated_duration_ms = max(100, task.estimated_duration_ms // 2)
        return tasks

    async def _generate_alternatives(
        self,
        goal: str,
        tasks: Dict[str, Task],
        context: Optional[str],
    ) -> List[Plan]:
        """توليد خطط بديلة."""
        # For now, return empty — can be enhanced with LLM
        return []

    def _calculate_plan_confidence(self, plan: Plan) -> float:
        """حساب ثقة الخطة."""
        if not plan.tasks:
            return 0.0

        # Factors: number of tasks, dependencies resolved, priority alignment
        num_tasks = len(plan.tasks)
        has_dependencies = any(len(t.dependencies) > 0 for t in plan.tasks.values())

        confidence = 0.5
        confidence += min(num_tasks * 0.05, 0.3)  # More tasks = more detailed
        if has_dependencies:
            confidence += 0.1

        return min(confidence, 1.0)

    # ── Execution Helpers ─────────────────────────────────────────────────

    def get_ready_tasks(self, plan: Plan) -> List[Task]:
        """الحصول على المهام الجاهزة للتنفيذ."""
        ready = []
        completed = {tid for tid, t in plan.tasks.items() if t.status == TaskStatus.COMPLETED}

        for task in plan.tasks.values():
            if task.status == TaskStatus.PENDING:
                if all(dep_id in completed for dep_id in task.dependencies):
                    task.status = TaskStatus.READY
                    ready.append(task)

        return ready

    def mark_completed(self, plan: Plan, task_id: str, result: Any = None):
        """تحديد مهمة كمكتملة."""
        if task_id in plan.tasks:
            plan.tasks[task_id].status = TaskStatus.COMPLETED
            plan.tasks[task_id].result = result

    def mark_failed(self, plan: Plan, task_id: str, error: str):
        """تحديد مهمة كفاشلة."""
        if task_id in plan.tasks:
            plan.tasks[task_id].status = TaskStatus.FAILED
            plan.tasks[task_id].error = error
            # Block dependent tasks
            for task in plan.tasks.values():
                if task_id in task.dependencies:
                    task.status = TaskStatus.BLOCKED


# ── Singleton ─────────────────────────────────────────────────────────────

_planning_engine: Optional[PlanningEngine] = None


def get_planning_engine(llm_manager=None) -> PlanningEngine:
    """الحصول على محرك التخطيط — Singleton."""
    global _planning_engine
    if _planning_engine is None:
        _planning_engine = PlanningEngine(llm_manager=llm_manager)
    return _planning_engine
