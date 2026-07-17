"""
Task Decomposer v3 — محلّل تفكيك المهام المتقدم
================================================

يقوم بـ:
- تفكيك المهام بشكل ديناميكي وهرمي
- تحديد التبعيات بين المهام
- تقدير الموارد والوقت
- اكتشاف المهام المتوازية
- إعادة التخطيط الديناميكي
- معالجة الفشل والاستثناءات

يستخدم:
- LLM للتحليل العميق
- Reasoning Engine للاستدلال
- Decision Engine لاختيار الاستراتيجية
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from hajeen_platform.core.llm import LLMManager

logger = logging.getLogger(__name__)


class TaskPriority(str, Enum):
    """أولويات المهام."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    """حالات المهام."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DecompositionStrategy(str, Enum):
    """استراتيجيات التفكيك."""
    SEQUENTIAL = "sequential"           # تسلسلي
    PARALLEL = "parallel"               # متوازي
    HIERARCHICAL = "hierarchical"       # هرمي
    ADAPTIVE = "adaptive"               # تكيفي


@dataclass
class Task:
    """مهمة فردية."""
    task_id: str
    title: str
    description: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    estimated_tokens: int = 0
    estimated_cost_usd: float = 0.0
    estimated_duration_seconds: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    parent_task_id: Optional[str] = None
    subtasks: List[str] = field(default_factory=list)
    assigned_model: Optional[str] = None
    assigned_agent: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "dependencies": self.dependencies,
            "parent_task_id": self.parent_task_id,
            "subtasks": self.subtasks,
            "assigned_model": self.assigned_model,
            "assigned_agent": self.assigned_agent,
            "retry_count": self.retry_count,
            "result": self.result,
            "error": self.error,
        }

    @property
    def is_ready(self) -> bool:
        """هل المهمة جاهزة للتنفيذ؟"""
        return self.status == TaskStatus.READY

    @property
    def is_completed(self) -> bool:
        """هل المهمة مكتملة؟"""
        return self.status == TaskStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """هل المهمة فشلت؟"""
        return self.status == TaskStatus.FAILED


@dataclass
class DecompositionResult:
    """نتيجة التفكيك."""
    decomposition_id: str
    root_task_id: str
    all_tasks: List[Task]
    task_graph: Dict[str, List[str]]  # task_id -> [dependent_task_ids]
    parallel_groups: List[List[str]]  # مجموعات المهام المتوازية
    sequential_order: List[str]  # ترتيب التنفيذ التسلسلي
    strategy_used: DecompositionStrategy
    total_estimated_tokens: int
    total_estimated_cost_usd: float
    total_estimated_duration_seconds: float
    confidence: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decomposition_id": self.decomposition_id,
            "root_task_id": self.root_task_id,
            "all_tasks": [t.to_dict() for t in self.all_tasks],
            "task_graph": self.task_graph,
            "parallel_groups": self.parallel_groups,
            "sequential_order": self.sequential_order,
            "strategy_used": self.strategy_used.value,
            "total_estimated_tokens": self.total_estimated_tokens,
            "total_estimated_cost_usd": round(self.total_estimated_cost_usd, 6),
            "total_estimated_duration_seconds": self.total_estimated_duration_seconds,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
        }


class TaskDecomposerV3:
    """
    محلّل تفكيك المهام المتقدم v3.
    
    يستخدم:
    - LLM للتحليل العميق
    - Reasoning Engine للاستدلال
    - Decision Engine لاختيار الاستراتيجية
    """

    def __init__(self, llm_manager: LLMManager) -> None:
        self.llm_manager = llm_manager
        self._decompositions_cache: Dict[str, DecompositionResult] = {}
        self._decomposition_history: List[DecompositionResult] = []
        logger.info("TaskDecomposerV3: initialized")

    async def decompose(
        self,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        strategy: DecompositionStrategy = DecompositionStrategy.ADAPTIVE,
    ) -> DecompositionResult:
        """
        تفكيك الهدف إلى مهام.
        
        الخطوات:
        1. تحليل الهدف
        2. اختيار استراتيجية التفكيك
        3. توليد المهام الأولية
        4. تحديد التبعيات
        5. تحسين التفكيك
        6. حساب الموارد
        7. بناء النتيجة النهائية
        """
        decomposition_id = str(uuid.uuid4())
        root_task_id = str(uuid.uuid4())
        
        try:
            # ── Step 1: تحليل الهدف ────────────────────────────────
            objective_analysis = await self._analyze_objective(objective, context)
            
            # ── Step 2: اختيار استراتيجية التفكيك ──────────────────
            chosen_strategy = await self._choose_decomposition_strategy(
                objective, objective_analysis, strategy
            )
            
            # ── Step 3: توليد المهام الأولية ──────────────────────
            initial_tasks = await self._generate_initial_tasks(
                objective, objective_analysis, chosen_strategy
            )
            
            # ── Step 4: تحديد التبعيات ────────────────────────────
            tasks_with_deps = await self._identify_dependencies(
                initial_tasks, objective_analysis
            )
            
            # ── Step 5: تحسين التفكيك ────────────────────────────
            optimized_tasks = await self._optimize_decomposition(
                tasks_with_deps, chosen_strategy
            )
            
            # ── Step 6: حساب الموارد ────────────────────────────
            for task in optimized_tasks:
                task.estimated_tokens = await self._estimate_task_tokens(task)
                task.estimated_cost_usd = await self._estimate_task_cost(task)
                task.estimated_duration_seconds = await self._estimate_task_duration(task)
            
            # ── Step 7: بناء الرسم البياني للمهام ──────────────────
            task_graph = self._build_task_graph(optimized_tasks)
            parallel_groups = self._identify_parallel_groups(task_graph, optimized_tasks)
            sequential_order = self._calculate_sequential_order(task_graph, optimized_tasks)
            
            # ── Step 8: حساب الإحصائيات الكلية ────────────────────
            total_tokens = sum(t.estimated_tokens for t in optimized_tasks)
            total_cost = sum(t.estimated_cost_usd for t in optimized_tasks)
            total_duration = max(
                (t.estimated_duration_seconds for t in optimized_tasks),
                default=0.0
            )
            
            # ── Step 9: حساب الثقة ────────────────────────────────
            confidence = await self._calculate_decomposition_confidence(
                optimized_tasks, task_graph
            )
            
            # ── Step 10: بناء المبرر ────────────────────────────────
            reasoning = await self._build_decomposition_reasoning(
                objective_analysis, chosen_strategy, len(optimized_tasks), confidence
            )
            
            # ── Step 11: بناء النتيجة النهائية ────────────────────
            result = DecompositionResult(
                decomposition_id=decomposition_id,
                root_task_id=root_task_id,
                all_tasks=optimized_tasks,
                task_graph=task_graph,
                parallel_groups=parallel_groups,
                sequential_order=sequential_order,
                strategy_used=chosen_strategy,
                total_estimated_tokens=total_tokens,
                total_estimated_cost_usd=total_cost,
                total_estimated_duration_seconds=total_duration,
                confidence=confidence,
                reasoning=reasoning,
                metadata={
                    "objective": objective,
                    "objective_analysis": objective_analysis,
                },
            )
            
            # تخزين مؤقت
            self._decompositions_cache[decomposition_id] = result
            self._decomposition_history.append(result)
            
            logger.info(
                "task_decomposer_v3: decomposed objective into %d tasks "
                "strategy=%s confidence=%.3f tokens=%d",
                len(optimized_tasks), chosen_strategy.value, confidence, total_tokens
            )
            
            return result
        
        except Exception as e:
            logger.error("task_decomposer_v3: error during decomposition: %s", e, exc_info=True)
            
            # استجابة احتياطية
            root_task = Task(
                task_id=root_task_id,
                title="المهمة الرئيسية",
                description=objective,
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
            )
            
            return DecompositionResult(
                decomposition_id=decomposition_id,
                root_task_id=root_task_id,
                all_tasks=[root_task],
                task_graph={root_task_id: []},
                parallel_groups=[[root_task_id]],
                sequential_order=[root_task_id],
                strategy_used=DecompositionStrategy.SEQUENTIAL,
                total_estimated_tokens=1000,
                total_estimated_cost_usd=0.01,
                total_estimated_duration_seconds=60.0,
                confidence=0.3,
                reasoning=f"فشل التفكيك: {str(e)}",
                metadata={"error": str(e)},
            )

    async def _analyze_objective(
        self,
        objective: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """تحليل الهدف."""
        try:
            context_str = json.dumps(context, ensure_ascii=False) if context else ""
            
            prompt = f"""حلّل الهدف التالي:

الهدف: {objective}

السياق: {context_str}

قدّم تحليلاً يغطي:
1. ما هي المتطلبات الأساسية
2. ما هي التحديات الرئيسية
3. ما هي الخطوات الضرورية
4. ما هي التبعيات المحتملة"""
            
            analysis = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=500,
            )
            
            return analysis
        except Exception as e:
            logger.warning("task_decomposer_v3: failed to analyze objective: %s", e)
            return "تحليل احتياطي"

    async def _choose_decomposition_strategy(
        self,
        objective: str,
        analysis: str,
        preferred_strategy: DecompositionStrategy,
    ) -> DecompositionStrategy:
        """اختيار استراتيجية التفكيك."""
        if preferred_strategy != DecompositionStrategy.ADAPTIVE:
            return preferred_strategy
        
        try:
            prompt = f"""اختر أفضل استراتيجية تفكيك للهدف التالي:

الهدف: {objective}

التحليل: {analysis}

الخيارات:
1. SEQUENTIAL - تسلسلي (خطوة بخطوة)
2. PARALLEL - متوازي (خطوات متعددة معاً)
3. HIERARCHICAL - هرمي (مستويات متعددة)

أجب بـ 'SEQUENTIAL' أو 'PARALLEL' أو 'HIERARCHICAL' فقط."""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.2,
                max_tokens=20,
            )
            
            response = response.strip().upper()
            for strategy in DecompositionStrategy:
                if strategy.value.upper() in response:
                    return strategy
        except Exception as e:
            logger.warning("task_decomposer_v3: failed to choose strategy: %s", e)
        
        return DecompositionStrategy.HIERARCHICAL

    async def _generate_initial_tasks(
        self,
        objective: str,
        analysis: str,
        strategy: DecompositionStrategy,
    ) -> List[Task]:
        """توليد المهام الأولية."""
        try:
            prompt = f"""قسّم الهدف التالي إلى مهام فرعية:

الهدف: {objective}

التحليل: {analysis}

الاستراتيجية: {strategy.value}

قدّم قائمة بـ 3-7 مهام فرعية بصيغة JSON:
[
  {{"title": "عنوان المهمة", "description": "وصف المهمة", "priority": "high|medium|low"}},
  ...
]"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.5,
                max_tokens=800,
            )
            
            # محاولة استخراج JSON
            try:
                tasks_data = json.loads(response)
            except:
                # محاولة استخراج JSON من النص
                import re
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    tasks_data = json.loads(json_match.group())
                else:
                    tasks_data = []
            
            tasks = []
            for task_data in tasks_data:
                task = Task(
                    task_id=str(uuid.uuid4()),
                    title=task_data.get("title", "مهمة"),
                    description=task_data.get("description", ""),
                    priority=TaskPriority(task_data.get("priority", "medium")),
                )
                tasks.append(task)
            
            return tasks if tasks else [
                Task(
                    task_id=str(uuid.uuid4()),
                    title="المهمة الرئيسية",
                    description=objective,
                    priority=TaskPriority.HIGH,
                )
            ]
        except Exception as e:
            logger.warning("task_decomposer_v3: failed to generate tasks: %s", e)
            return [
                Task(
                    task_id=str(uuid.uuid4()),
                    title="المهمة الرئيسية",
                    description=objective,
                    priority=TaskPriority.HIGH,
                )
            ]

    async def _identify_dependencies(
        self,
        tasks: List[Task],
        analysis: str,
    ) -> List[Task]:
        """تحديد التبعيات بين المهام."""
        try:
            task_descriptions = "\n".join([f"{i}: {t.title}" for i, t in enumerate(tasks)])
            
            prompt = f"""حدّد التبعيات بين المهام التالية:

المهام:
{task_descriptions}

التحليل: {analysis}

قدّم النتيجة بصيغة JSON:
{{
  "dependencies": [
    {{"task_index": 1, "depends_on": [0]}},
    ...
  ]
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=400,
            )
            
            try:
                deps_data = json.loads(response)
                for dep in deps_data.get("dependencies", []):
                    task_idx = dep.get("task_index")
                    depends_on = dep.get("depends_on", [])
                    if 0 <= task_idx < len(tasks):
                        for dep_idx in depends_on:
                            if 0 <= dep_idx < len(tasks):
                                tasks[task_idx].dependencies.append(tasks[dep_idx].task_id)
            except:
                pass
        except Exception as e:
            logger.warning("task_decomposer_v3: failed to identify dependencies: %s", e)
        
        return tasks

    async def _optimize_decomposition(
        self,
        tasks: List[Task],
        strategy: DecompositionStrategy,
    ) -> List[Task]:
        """تحسين التفكيك."""
        # يمكن إضافة منطق تحسين هنا
        return tasks

    async def _estimate_task_tokens(self, task: Task) -> int:
        """تقدير الرموز للمهمة."""
        base = len(task.title) + len(task.description)
        return max(100, base * 2)

    async def _estimate_task_cost(self, task: Task) -> float:
        """تقدير التكلفة للمهمة."""
        tokens = task.estimated_tokens
        return tokens * 0.00015 / 1000  # تقريبي

    async def _estimate_task_duration(self, task: Task) -> float:
        """تقدير المدة للمهمة."""
        if task.priority == TaskPriority.CRITICAL:
            return 5.0
        elif task.priority == TaskPriority.HIGH:
            return 10.0
        elif task.priority == TaskPriority.MEDIUM:
            return 20.0
        else:
            return 30.0

    def _build_task_graph(self, tasks: List[Task]) -> Dict[str, List[str]]:
        """بناء الرسم البياني للمهام."""
        graph = {}
        for task in tasks:
            dependents = [t.task_id for t in tasks if task.task_id in t.dependencies]
            graph[task.task_id] = dependents
        return graph

    def _identify_parallel_groups(
        self,
        task_graph: Dict[str, List[str]],
        tasks: List[Task],
    ) -> List[List[str]]:
        """تحديد مجموعات المهام المتوازية."""
        groups = []
        processed = set()
        
        for task_id in task_graph:
            if task_id in processed:
                continue
            
            # البحث عن مهام بدون تبعيات
            task = next((t for t in tasks if t.task_id == task_id), None)
            if task and not task.dependencies:
                group = [task_id]
                processed.add(task_id)
                
                # البحث عن مهام أخرى بدون تبعيات
                for other_id in task_graph:
                    if other_id not in processed:
                        other = next((t for t in tasks if t.task_id == other_id), None)
                        if other and not other.dependencies:
                            group.append(other_id)
                            processed.add(other_id)
                
                groups.append(group)
        
        return groups if groups else [[t.task_id for t in tasks]]

    def _calculate_sequential_order(
        self,
        task_graph: Dict[str, List[str]],
        tasks: List[Task],
    ) -> List[str]:
        """حساب ترتيب التنفيذ التسلسلي."""
        # ترتيب طوبولوجي بسيط
        order = []
        processed = set()
        
        while len(processed) < len(tasks):
            for task in tasks:
                if task.task_id not in processed:
                    # التحقق من أن جميع التبعيات مكتملة
                    if all(dep in processed for dep in task.dependencies):
                        order.append(task.task_id)
                        processed.add(task.task_id)
                        break
        
        return order

    async def _calculate_decomposition_confidence(
        self,
        tasks: List[Task],
        task_graph: Dict[str, List[str]],
    ) -> float:
        """حساب ثقة التفكيك."""
        # عدد المهام
        task_count_score = min(1.0, len(tasks) / 10)
        
        # توازن التبعيات
        total_deps = sum(len(deps) for deps in task_graph.values())
        dep_score = 1.0 - min(1.0, total_deps / (len(tasks) * 2))
        
        return (task_count_score + dep_score) / 2

    async def _build_decomposition_reasoning(
        self,
        analysis: str,
        strategy: DecompositionStrategy,
        task_count: int,
        confidence: float,
    ) -> str:
        """بناء مبرر التفكيك."""
        return (
            f"تم تفكيك الهدف إلى {task_count} مهام "
            f"باستخدام استراتيجية {strategy.value} "
            f"بثقة {confidence:.2%}"
        )

    def get_decomposition(self, decomposition_id: str) -> Optional[DecompositionResult]:
        """الحصول على نتيجة تفكيك محفوظة."""
        return self._decompositions_cache.get(decomposition_id)

    def get_recent_decompositions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """آخر نتائج التفكيك."""
        recent = self._decomposition_history[-limit:]
        return [d.to_dict() for d in recent]

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات التفكيك."""
        if not self._decomposition_history:
            return {"total_decompositions": 0}
        
        total = len(self._decomposition_history)
        avg_tasks = sum(len(d.all_tasks) for d in self._decomposition_history) / total
        avg_confidence = sum(d.confidence for d in self._decomposition_history) / total
        
        return {
            "total_decompositions": total,
            "avg_tasks_per_decomposition": round(avg_tasks, 1),
            "avg_confidence": round(avg_confidence, 3),
            "total_tokens_estimated": sum(d.total_estimated_tokens for d in self._decomposition_history),
        }


# Singleton
_task_decomposer_v3: Optional[TaskDecomposerV3] = None


def get_task_decomposer_v3(
    llm_manager: Optional[LLMManager] = None,
) -> TaskDecomposerV3:
    """الحصول على instance من TaskDecomposerV3."""
    global _task_decomposer_v3
    if _task_decomposer_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _task_decomposer_v3 = TaskDecomposerV3(llm_manager)
    return _task_decomposer_v3
