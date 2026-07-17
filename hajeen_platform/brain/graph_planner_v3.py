"""
Graph Planner v3 — مخطط الرسم البياني المتقدم
==============================================

يقوم بـ:
- بناء خطط تنفيذ معقدة
- دعم التنفيذ الشرطي
- معالجة الأخطاء والاستثناءات
- إعادة المحاولة الذكية
- التعافي من الفشل
- تحسين الأداء
- تتبع التقدم

يستخدم:
- LLM للاستدلال
- Task Decomposer لتفكيك المهام
- Decision Engine لاختيار الاستراتيجية
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from hajeen_platform.core.llm import LLMManager
from hajeen_platform.brain.task_decomposer_v3 import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class ExecutionNodeType(str, Enum):
    """أنواع عقد التنفيذ."""
    TASK = "task"
    DECISION = "decision"
    PARALLEL = "parallel"
    RETRY = "retry"
    FALLBACK = "fallback"
    MERGE = "merge"


class ConditionType(str, Enum):
    """أنواع الشروط."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    QUALITY_THRESHOLD = "quality_threshold"
    CUSTOM = "custom"


@dataclass
class Condition:
    """شرط تنفيذي."""
    condition_type: ConditionType
    expression: str  # التعبير الشرطي
    threshold: Optional[float] = None
    custom_check: Optional[Callable] = None

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """تقييم الشرط."""
        try:
            if self.condition_type == ConditionType.SUCCESS:
                return context.get("status") == "success"
            elif self.condition_type == ConditionType.FAILURE:
                return context.get("status") == "failure"
            elif self.condition_type == ConditionType.TIMEOUT:
                return context.get("elapsed_time", 0) > context.get("timeout", float('inf'))
            elif self.condition_type == ConditionType.QUALITY_THRESHOLD:
                return context.get("quality_score", 0) >= (self.threshold or 0.7)
            elif self.condition_type == ConditionType.CUSTOM:
                if self.custom_check:
                    return await self.custom_check(context)
            return True
        except Exception as e:
            logger.warning("condition_evaluation_failed: %s", e)
            return False


@dataclass
class ExecutionEdge:
    """حافة بين عقد التنفيذ."""
    from_node_id: str
    to_node_id: str
    condition: Optional[Condition] = None
    weight: float = 1.0  # لأغراض التحسين


@dataclass
class ExecutionNode:
    """عقدة في رسم بياني التنفيذ."""
    node_id: str
    node_type: ExecutionNodeType
    task: Optional[Task] = None
    condition: Optional[Condition] = None
    retry_policy: Optional[Dict[str, Any]] = None
    fallback_node_id: Optional[str] = None
    timeout_seconds: float = 300.0
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "task_id": self.task.task_id if self.task else None,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "quality_score": round(self.quality_score, 3),
        }


@dataclass
class ExecutionPlan:
    """خطة تنفيذ كاملة."""
    plan_id: str
    root_node_id: str
    all_nodes: Dict[str, ExecutionNode]
    edges: List[ExecutionEdge]
    execution_order: List[str]  # ترتيب التنفيذ الأولي
    parallel_groups: List[List[str]]  # مجموعات التنفيذ المتوازي
    total_estimated_duration_seconds: float
    total_estimated_cost_usd: float
    confidence: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "root_node_id": self.root_node_id,
            "all_nodes": {nid: n.to_dict() for nid, n in self.all_nodes.items()},
            "execution_order": self.execution_order,
            "parallel_groups": self.parallel_groups,
            "total_estimated_duration_seconds": self.total_estimated_duration_seconds,
            "total_estimated_cost_usd": round(self.total_estimated_cost_usd, 6),
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
        }


class GraphPlannerV3:
    """
    مخطط الرسم البياني المتقدم v3.
    
    يستخدم:
    - LLM للاستدلال
    - Task Decomposer لتفكيك المهام
    - Decision Engine لاختيار الاستراتيجية
    """

    def __init__(self, llm_manager: LLMManager) -> None:
        self.llm_manager = llm_manager
        self._plans_cache: Dict[str, ExecutionPlan] = {}
        self._plan_history: List[ExecutionPlan] = []
        logger.info("GraphPlannerV3: initialized")

    async def plan(
        self,
        tasks: List[Task],
        task_graph: Dict[str, List[str]],
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """
        بناء خطة تنفيذ.
        
        الخطوات:
        1. تحليل المهام والتبعيات
        2. بناء عقد التنفيذ
        3. إضافة شروط التنفيذ
        4. إضافة سياسات إعادة المحاولة
        5. إضافة آليات الفشل
        6. حساب ترتيب التنفيذ
        7. تحسين الخطة
        8. حساب الموارد والثقة
        """
        plan_id = str(uuid.uuid4())
        root_node_id = str(uuid.uuid4())
        
        try:
            # ── Step 1: تحليل المهام والتبعيات ──────────────────
            analysis = await self._analyze_tasks_and_dependencies(tasks, task_graph)
            
            # ── Step 2: بناء عقد التنفيذ ──────────────────────────
            nodes = await self._build_execution_nodes(tasks, analysis)
            
            # ── Step 3: إضافة شروط التنفيذ ──────────────────────
            nodes = await self._add_execution_conditions(nodes, task_graph)
            
            # ── Step 4: إضافة سياسات إعادة المحاولة ──────────────
            nodes = await self._add_retry_policies(nodes, analysis)
            
            # ── Step 5: إضافة آليات الفشل ──────────────────────
            nodes = await self._add_fallback_mechanisms(nodes, tasks)
            
            # ── Step 6: بناء الحواف ────────────────────────────
            edges = await self._build_execution_edges(nodes, task_graph)
            
            # ── Step 7: حساب ترتيب التنفيذ ────────────────────
            execution_order = self._calculate_execution_order(nodes, edges)
            parallel_groups = self._identify_parallel_groups(nodes, edges)
            
            # ── Step 8: تحسين الخطة ────────────────────────────
            nodes, edges = await self._optimize_plan(nodes, edges)
            
            # ── Step 9: حساب الموارد والثقة ────────────────────
            total_duration = sum(t.timeout_seconds for t in tasks)
            total_cost = sum(t.estimated_cost_usd for t in tasks)
            confidence = await self._calculate_plan_confidence(nodes, edges)
            
            # ── Step 10: بناء المبرر ────────────────────────────
            reasoning = await self._build_plan_reasoning(
                len(nodes), len(edges), confidence
            )
            
            # ── Step 11: بناء الخطة النهائية ────────────────────
            nodes_dict = {n.node_id: n for n in nodes}
            
            plan = ExecutionPlan(
                plan_id=plan_id,
                root_node_id=root_node_id,
                all_nodes=nodes_dict,
                edges=edges,
                execution_order=execution_order,
                parallel_groups=parallel_groups,
                total_estimated_duration_seconds=total_duration,
                total_estimated_cost_usd=total_cost,
                confidence=confidence,
                reasoning=reasoning,
                metadata={
                    "task_count": len(tasks),
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                },
            )
            
            # تخزين مؤقت
            self._plans_cache[plan_id] = plan
            self._plan_history.append(plan)
            
            logger.info(
                "graph_planner_v3: created execution plan nodes=%d edges=%d confidence=%.3f",
                len(nodes), len(edges), confidence
            )
            
            return plan
        
        except Exception as e:
            logger.error("graph_planner_v3: error during planning: %s", e, exc_info=True)
            
            # خطة احتياطية بسيطة
            root_node = ExecutionNode(
                node_id=root_node_id,
                node_type=ExecutionNodeType.TASK,
                task=tasks[0] if tasks else None,
            )
            
            return ExecutionPlan(
                plan_id=plan_id,
                root_node_id=root_node_id,
                all_nodes={root_node_id: root_node},
                edges=[],
                execution_order=[root_node_id],
                parallel_groups=[[root_node_id]],
                total_estimated_duration_seconds=300.0,
                total_estimated_cost_usd=0.01,
                confidence=0.3,
                reasoning=f"فشل التخطيط: {str(e)}",
                metadata={"error": str(e)},
            )

    async def _analyze_tasks_and_dependencies(
        self,
        tasks: List[Task],
        task_graph: Dict[str, List[str]],
    ) -> str:
        """تحليل المهام والتبعيات."""
        try:
            task_list = "\n".join([f"- {t.title}" for t in tasks])
            
            prompt = f"""حلّل المهام والتبعيات التالية:

المهام:
{task_list}

عدد المهام: {len(tasks)}
عدد التبعيات: {sum(len(deps) for deps in task_graph.values())}

قدّم تحليلاً موجزاً يغطي:
1. التحديات الرئيسية
2. نقاط الاختناق المحتملة
3. فرص التحسين"""
            
            analysis = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=400,
            )
            
            return analysis
        except Exception as e:
            logger.warning("graph_planner_v3: failed to analyze: %s", e)
            return "تحليل احتياطي"

    async def _build_execution_nodes(
        self,
        tasks: List[Task],
        analysis: str,
    ) -> List[ExecutionNode]:
        """بناء عقد التنفيذ."""
        nodes = []
        
        for task in tasks:
            node = ExecutionNode(
                node_id=str(uuid.uuid4()),
                node_type=ExecutionNodeType.TASK,
                task=task,
                timeout_seconds=task.estimated_duration_seconds + 60,
            )
            nodes.append(node)
        
        return nodes

    async def _add_execution_conditions(
        self,
        nodes: List[ExecutionNode],
        task_graph: Dict[str, List[str]],
    ) -> List[ExecutionNode]:
        """إضافة شروط التنفيذ."""
        for node in nodes:
            if node.task:
                # شرط النجاح الافتراضي
                node.condition = Condition(
                    condition_type=ConditionType.SUCCESS,
                    expression="status == 'success'",
                )
        
        return nodes

    async def _add_retry_policies(
        self,
        nodes: List[ExecutionNode],
        analysis: str,
    ) -> List[ExecutionNode]:
        """إضافة سياسات إعادة المحاولة."""
        for node in nodes:
            if node.task and node.task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
                node.retry_policy = {
                    "strategy": "exponential_backoff",
                    "max_retries": 3,
                    "initial_delay_seconds": 1,
                    "max_delay_seconds": 30,
                }
            else:
                node.retry_policy = {
                    "strategy": "linear_backoff",
                    "max_retries": 2,
                    "initial_delay_seconds": 1,
                }
        
        return nodes

    async def _add_fallback_mechanisms(
        self,
        nodes: List[ExecutionNode],
        tasks: List[Task],
    ) -> List[ExecutionNode]:
        """إضافة آليات الفشل."""
        # إضافة عقد fallback للمهام الحرجة
        for i, node in enumerate(nodes):
            if node.task and node.task.priority == TaskPriority.CRITICAL:
                # إنشاء عقدة fallback
                fallback_node = ExecutionNode(
                    node_id=str(uuid.uuid4()),
                    node_type=ExecutionNodeType.FALLBACK,
                    task=Task(
                        task_id=str(uuid.uuid4()),
                        title=f"Fallback: {node.task.title}",
                        description=f"خطة احتياطية لـ {node.task.title}",
                        priority=TaskPriority.HIGH,
                    ),
                )
                node.fallback_node_id = fallback_node.node_id
                nodes.append(fallback_node)
        
        return nodes

    async def _build_execution_edges(
        self,
        nodes: List[ExecutionNode],
        task_graph: Dict[str, List[str]],
    ) -> List[ExecutionEdge]:
        """بناء الحواف بين العقد."""
        edges = []
        
        # بناء خريطة من task_id إلى node_id
        task_to_node = {}
        for node in nodes:
            if node.task:
                task_to_node[node.task.task_id] = node.node_id
        
        # بناء الحواف بناءً على التبعيات
        for task_id, dependents in task_graph.items():
            if task_id in task_to_node:
                from_node_id = task_to_node[task_id]
                for dependent_id in dependents:
                    if dependent_id in task_to_node:
                        to_node_id = task_to_node[dependent_id]
                        edge = ExecutionEdge(
                            from_node_id=from_node_id,
                            to_node_id=to_node_id,
                            condition=Condition(
                                condition_type=ConditionType.SUCCESS,
                                expression="status == 'success'",
                            ),
                        )
                        edges.append(edge)
        
        return edges

    def _calculate_execution_order(
        self,
        nodes: List[ExecutionNode],
        edges: List[ExecutionEdge],
    ) -> List[str]:
        """حساب ترتيب التنفيذ."""
        # ترتيب طوبولوجي بسيط
        order = []
        processed = set()
        
        # إيجاد العقد بدون تبعيات
        incoming = {n.node_id: 0 for n in nodes}
        for edge in edges:
            incoming[edge.to_node_id] += 1
        
        # إضافة العقد بدون تبعيات
        queue = [n.node_id for n in nodes if incoming[n.node_id] == 0]
        
        while queue:
            node_id = queue.pop(0)
            order.append(node_id)
            processed.add(node_id)
            
            # إضافة العقد التالية
            for edge in edges:
                if edge.from_node_id == node_id:
                    incoming[edge.to_node_id] -= 1
                    if incoming[edge.to_node_id] == 0:
                        queue.append(edge.to_node_id)
        
        return order

    def _identify_parallel_groups(
        self,
        nodes: List[ExecutionNode],
        edges: List[ExecutionEdge],
    ) -> List[List[str]]:
        """تحديد مجموعات التنفيذ المتوازي."""
        groups = []
        processed = set()
        
        # إيجاد العقد بدون تبعيات
        incoming = {n.node_id: 0 for n in nodes}
        for edge in edges:
            incoming[edge.to_node_id] += 1
        
        # أول مجموعة: العقد بدون تبعيات
        first_group = [n.node_id for n in nodes if incoming[n.node_id] == 0]
        if first_group:
            groups.append(first_group)
            processed.update(first_group)
        
        return groups if groups else [[n.node_id for n in nodes]]

    async def _optimize_plan(
        self,
        nodes: List[ExecutionNode],
        edges: List[ExecutionEdge],
    ) -> tuple[List[ExecutionNode], List[ExecutionEdge]]:
        """تحسين الخطة."""
        # يمكن إضافة منطق تحسين هنا
        return nodes, edges

    async def _calculate_plan_confidence(
        self,
        nodes: List[ExecutionNode],
        edges: List[ExecutionEdge],
    ) -> float:
        """حساب ثقة الخطة."""
        # عدد العقد والحواف
        node_score = min(1.0, len(nodes) / 20)
        edge_score = min(1.0, len(edges) / 30)
        
        return (node_score + edge_score) / 2

    async def _build_plan_reasoning(
        self,
        node_count: int,
        edge_count: int,
        confidence: float,
    ) -> str:
        """بناء مبرر الخطة."""
        return (
            f"تم بناء خطة تنفيذ مع {node_count} عقدة و {edge_count} حافة "
            f"بثقة {confidence:.2%}"
        )

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """الحصول على خطة محفوظة."""
        return self._plans_cache.get(plan_id)

    def get_recent_plans(self, limit: int = 10) -> List[Dict[str, Any]]:
        """آخر الخطط."""
        recent = self._plan_history[-limit:]
        return [p.to_dict() for p in recent]

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات التخطيط."""
        if not self._plan_history:
            return {"total_plans": 0}
        
        total = len(self._plan_history)
        avg_nodes = sum(len(p.all_nodes) for p in self._plan_history) / total
        avg_edges = sum(len(p.edges) for p in self._plan_history) / total
        avg_confidence = sum(p.confidence for p in self._plan_history) / total
        
        return {
            "total_plans": total,
            "avg_nodes_per_plan": round(avg_nodes, 1),
            "avg_edges_per_plan": round(avg_edges, 1),
            "avg_confidence": round(avg_confidence, 3),
        }


# Singleton
_graph_planner_v3: Optional[GraphPlannerV3] = None


def get_graph_planner_v3(
    llm_manager: Optional[LLMManager] = None,
) -> GraphPlannerV3:
    """الحصول على instance من GraphPlannerV3."""
    global _graph_planner_v3
    if _graph_planner_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _graph_planner_v3 = GraphPlannerV3(llm_manager)
    return _graph_planner_v3
