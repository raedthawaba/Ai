"""
Planning Engine - Orchestrator
=============================
المنسق الرئيسي لجميع مكونات التخطيط.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .goal_manager import GoalManager, Goal
from .task_decomposer import TaskDecomposer, DecompositionPlan, MicroTask
from .graph_planner import GraphPlanner, ExecutionGraph
from .plan_validator import PlanValidator, AdaptiveReplanner, ValidationResult
from .progress_tracker import ProgressTracker, TaskStatus
from .production_infra import CircuitBreaker, RateLimiter, SmartCache
from .autonomous_planner import (
    AutonomousPlanningEngine, PlanningMode, HierarchicalPlanner, RecursivePlanner
)
from .decision_engine import ResourceType, ResourceAllocation, RetryStrategy

logger = logging.getLogger(__name__)


@dataclass
class PlanningConfig:
    max_tasks: int = 1000
    max_depth: int = 10
    enable_validation: bool = True
    enable_adaptive_replan: bool = True
    enable_circuit_breaker: bool = True
    circuit_failure_threshold: int = 5


@dataclass
class PlanningResult:
    success: bool
    goal: Optional[Goal] = None
    plan: Optional[DecompositionPlan] = None
    graph: Optional[ExecutionGraph] = None
    validation: Optional[ValidationResult] = None
    resource_allocation: Optional[ResourceAllocation] = None
    execution_order: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    replanned: bool = False


class PlanningEngine:
    """
    محرك التخطيط الموحد - المنسق الرئيسي.
    
    مسار التنفيذ:
    BrainV3.process()
        ↓
    PlanningEngine.execute()
        ↓
    GoalManager.analyze()
        ↓
    TaskDecomposer.decompose()
        ↓
    GraphPlanner.build_graph()
        ↓
    PlanValidator.validate()
        ↓
    ResourcePlanner.allocate()
        ↓
    RiskAnalyzer.analyze()
        ↓
    AlternativePlanner.alternatives()
        ↓
    DecisionEngine.decide()
        ↓
    Execution
        ↓
    PlanningResult
    """

    def __init__(self, config: Optional[PlanningConfig] = None) -> None:
        self.config = config or PlanningConfig()
        
        # المكوّنات
        self.goal_manager = GoalManager()
        self.task_decomposer = TaskDecomposer()
        self.graph_planner = GraphPlanner()
        self.plan_validator = PlanValidator()
        self.replanner = AdaptiveReplanner()
        self.progress_tracker = ProgressTracker()
        self.autonomous_engine = AutonomousPlanningEngine()
        # Note: DecisionEngineV3 requires llm_manager, will be initialized lazily
        self._decision_engine = None
        
        # Production components
        self.circuit_breaker = CircuitBreaker("planning_engine")
        self.rate_limiter = RateLimiter(max_calls=100, period_seconds=60)
        self.cache = SmartCache(max_size=1000)
        
        # Metrics
        self._total_plans = 0
        self._successful_plans = 0
        self._failed_plans = 0
        self._replans = 0

    async def execute(self, request: str, context: Optional[Dict] = None) -> PlanningResult:
        """
        تنفيذ التخطيط الكامل - المنسق الرئيسي.
        
        Args:
            request: طلب المستخدم
            context: سياق إضافي
            
        Returns:
            PlanningResult: النتيجة الكاملة مع جميع البيانات
        """
        start_time = time.time()
        result = PlanningResult(success=False)
        
        self._total_plans += 1
        
        try:
            # 1. Goal Management
            goal = await self.goal_manager.analyze(request)
            result.goal = goal
            logger.info(f"planning_engine: goal={goal.goal_id}")
            
            # 2. Task Decomposition
            plan = await self.task_decomposer.decompose(goal)
            result.plan = plan
            logger.info(f"planning_engine: plan={plan.plan_id}, tasks={len(plan.tasks)}")
            
            # 3. Graph Planning
            graph = await self.graph_planner.build_graph(plan)
            result.graph = graph
            logger.info(f"planning_engine: graph nodes={len(graph.nodes)}")
            
            # 4. Validation
            if self.config.enable_validation:
                validation = await self.plan_validator.validate(plan, graph)
                result.validation = validation
                
                # 5. Adaptive Replanning if needed
                if not validation.is_valid and self.config.enable_adaptive_replan:
                    plan, graph, repairs = await self.replanner.repair(plan, graph, validation.errors)
                    result.plan = plan
                    result.graph = graph
                    result.replanned = True
                    self._replans += 1
                    result.errors.extend(repairs)
                    logger.info(f"planning_engine: replanned with {len(repairs)} repairs")
            
            # 6. Resource Planning
            resource_alloc = await self._plan_resources(plan, context or {})
            result.resource_allocation = resource_alloc
            
            # 7. Execution Order
            result.execution_order = self._get_execution_order(graph)
            
            # 8. Decision Engine
            decision = await self._make_decision(plan, resource_alloc)
            
            # Success
            result.success = True
            self._successful_plans += 1
            
        except Exception as e:
            result.errors.append(str(e))
            self._failed_plans += 1
            logger.error(f"planning_engine: failed - {e}")
        
        # Metrics
        result.metrics = {
            "duration_ms": (time.time() - start_time) * 1000,
            "total_plans": self._total_plans,
            "successful": self._successful_plans,
            "failed": self._failed_plans,
            "replans": self._replans,
        }
        
        return result

    async def execute_with_autonomous(
        self, request: str, mode: PlanningMode = PlanningMode.AUTONOMOUS
    ) -> PlanningResult:
        """تنفيذ مع محرك التخطيط المستقل."""
        start_time = time.time()
        result = PlanningResult(success=False)
        
        try:
            # Goal analysis
            goal = await self.goal_manager.analyze(request)
            result.goal = goal
            
            # Autonomous planning
            auto_plan = await self.autonomous_engine.plan(goal, mode=mode)
            result.plan = auto_plan.sub_plans[0] if auto_plan.sub_plans else None
            result.graph = auto_plan.execution_graph
            result.validation = auto_plan.validation_result
            
            result.success = True
            
        except Exception as e:
            result.errors.append(str(e))
        
        result.metrics = {
            "duration_ms": (time.time() - start_time) * 1000,
            "mode": mode.value,
        }
        
        return result

    async def _plan_resources(
        self, plan: DecompositionPlan, context: Dict
    ) -> ResourceAllocation:
        """تخطيط الموارد."""
        # تقدير الموارد
        total_tokens = plan.total_estimated_tokens
        task_count = len(plan.tasks)
        
        # تحديد نوع المورد
        if task_count > 50:
            resource_type = ResourceType.CLOUD_MODEL
        elif task_count > 10:
            resource_type = ResourceType.MULTI_MODEL
        else:
            resource_type = ResourceType.LOCAL_MODEL
        
        return ResourceAllocation(
            resource_id=str(uuid.uuid4()),
            resource_type=resource_type,
            primary_model="gpt-4o",
            fallback_models=["gpt-4o-mini"],
            use_rag=total_tokens > 5000,
            use_web=False,
            use_multi_model=task_count > 20,
            collaborating_models=[],
            max_retries=3,
            retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            execution_order="parallel" if plan.can_parallelize else "sequential",
            parallel_limit=5 if plan.can_parallelize else 1,
            estimated_tokens=total_tokens,
            estimated_cost_usd=total_tokens * 0.00001,
            confidence=0.85,
            reasoning="Resource allocation based on task count and complexity"
        )

    async def _make_decision(
        self, plan: DecompositionPlan, allocation: ResourceAllocation
    ) -> Dict[str, Any]:
        """اتخاذ القرار النهائي (بدون DecisionEngineV3 للتبسيط)."""
        # تحليل المخاطر
        risk_score = len(plan.tasks) * 0.01
        if risk_score > 0.5:
            risk_score = 0.5
        
        return {
            "approved": plan.total_estimated_tokens < self.config.max_tasks * 100,
            "risk_score": risk_score,
            "allocation": allocation,
            "execution_mode": allocation.execution_order,
        }

    def _get_execution_order(self, graph: ExecutionGraph) -> List[str]:
        """الحصول على ترتيب التنفيذ."""
        return list(graph.nodes.keys())

    def get_metrics(self) -> Dict[str, Any]:
        """الحصول على المقاييس."""
        return {
            "total_plans": self._total_plans,
            "successful": self._successful_plans,
            "failed": self._failed_plans,
            "replans": self._replans,
            "success_rate": self._successful_plans / max(1, self._total_plans),
        }


# Singleton
_engine: Optional[PlanningEngine] = None


def get_planning_engine() -> PlanningEngine:
    global _engine
    if _engine is None:
        _engine = PlanningEngine()
    return _engine
