"""
Planning Engine v1.0
====================

The main Planning Engine that orchestrates all planning components.
Transforms reasoning results into executable plans.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core.base import BaseComponent, PlanningContext
from .core.models import (
    Plan, PlanStatus, PlanValidation, PlanningResult,
    Goal, GoalTree, GoalPriority, GoalStatus,
    Task, TaskGraph, ExecutionGraph,
    RiskAnalysis, AlternativePlan, ExecutionStrategyType,
    Resource
)

# Import all components
from .goal_manager.goal_manager import GoalManager, get_goal_manager
from .task_decomposer.task_decomposer import TaskDecomposer, get_task_decomposer
from .graph_planner.graph_planner import GraphPlanner, get_graph_planner
from .constraint_solver.constraint_solver import ConstraintSolver, get_constraint_solver
from .resource_planner.resource_planner import ResourcePlanner, get_resource_planner
from .scheduler.scheduler import Scheduler, get_scheduler
from .risk_analyzer.risk_analyzer import RiskAnalyzer, get_risk_analyzer
from .alternative_planner.alternative_planner import (
    AlternativePlanner, get_alternative_planner,
    PlanValidator, get_plan_validator,
    ExecutionStrategySelector, get_execution_strategy_selector,
    ReplanningEngine, get_replanning_engine,
    ProgressTracker, get_progress_tracker,
    CompletionAnalyzer, get_completion_analyzer
)


class PlanningEngine(BaseComponent):
    """
    Main Planning Engine.
    
    Transforms Reasoning Engine output into executable plans.
    
    Pipeline:
    1. Goal Creation - Create goals from reasoning results
    2. Task Decomposition - Break goals into tasks
    3. Dependency Detection - Build task graph
    4. Resource Planning - Allocate resources
    5. Risk Analysis - Identify and assess risks
    6. Plan Generation - Create execution plan
    7. Validation - Verify plan correctness
    8. Alternative Generation - Create backup plans
    """
    
    def __init__(self):
        super().__init__()
        
        # Initialize all components
        self._goal_manager = get_goal_manager()
        self._task_decomposer = get_task_decomposer()
        self._graph_planner = get_graph_planner()
        self._constraint_solver = get_constraint_solver()
        self._resource_planner = get_resource_planner()
        self._scheduler = get_scheduler()
        self._risk_analyzer = get_risk_analyzer()
        self._alternative_planner = get_alternative_planner()
        self._plan_validator = get_plan_validator()
        self._strategy_selector = get_execution_strategy_selector()
        self._replanning_engine = get_replanning_engine()
        self._progress_tracker = get_progress_tracker()
        self._completion_analyzer = get_completion_analyzer()
        
        self._current_plan: Optional[Plan] = None
    
    async def _async_initialize(self) -> None:
        """Initialize all components."""
        await self._goal_manager.initialize()
        await self._task_decomposer.initialize()
        await self._graph_planner.initialize()
        await self._constraint_solver.initialize()
        await self._resource_planner.initialize()
        await self._scheduler.initialize()
        await self._risk_analyzer.initialize()
        await self._alternative_planner.initialize()
        await self._plan_validator.initialize()
        await self._strategy_selector.initialize()
        await self._replanning_engine.initialize()
        await self._progress_tracker.initialize()
        await self._completion_analyzer.initialize()
        
        self.logger.info("PlanningEngine fully initialized")
    
    # =========================================================================
    # MAIN PLANNING METHOD
    # =========================================================================
    
    async def plan(
        self,
        reasoning_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> PlanningResult:
        """
        Main planning method.
        
        Transforms reasoning results into an executable plan.
        
        Args:
            reasoning_result: Output from Reasoning Engine
            context: Additional planning context
            
        Returns:
            PlanningResult with complete execution plan
        """
        start_time = time.time()
        
        self.logger.info("Starting planning process")
        
        # Create planning context
        plan_context = PlanningContext(
            reasoning_result=reasoning_result,
            config=context or {},
            current_phase="init"
        )
        
        # Phase 1: Create Goals
        plan_context.current_phase = "goal_creation"
        goal_tree = await self._create_goals(reasoning_result)
        plan_context.goal_tree = goal_tree
        plan_context.add_result("goals", goal_tree)
        
        # Phase 2: Decompose to Tasks
        plan_context.current_phase = "task_decomposition"
        task_graph = await self._decompose_tasks(goal_tree, reasoning_result)
        plan_context.task_graph = task_graph
        plan_context.add_result("tasks", task_graph)
        
        # Phase 3: Build Execution Graph
        plan_context.current_phase = "graph_building"
        execution_graph = self._build_execution_graph(task_graph)
        plan_context.add_result("execution_graph", execution_graph)
        
        # Phase 4: Analyze Risks
        plan_context.current_phase = "risk_analysis"
        risk_analysis = self._risk_analyzer.analyze(task_graph, context)
        plan_context.add_result("risks", risk_analysis)
        
        # Phase 5: Validate Plan
        plan_context.current_phase = "validation"
        validation = self._plan_validator.validate(task_graph, execution_graph)
        
        # Phase 6: Select Strategy
        plan_context.current_phase = "strategy_selection"
        strategy = self._strategy_selector.select(task_graph, context)
        
        # Phase 7: Generate Alternatives
        plan_context.current_phase = "alternatives"
        alternatives = self._alternative_planner.generate_alternatives(task_graph)
        
        # Phase 8: Create Final Plan
        plan_context.current_phase = "plan_creation"
        plan = await self._create_plan(
            goal_tree=goal_tree,
            task_graph=task_graph,
            execution_graph=execution_graph,
            risk_analysis=risk_analysis,
            validation=validation,
            strategy=strategy,
            alternatives=alternatives,
            reasoning_result=reasoning_result
        )
        
        self._current_plan = plan
        
        # Calculate metrics
        planning_duration = time.time() - start_time
        
        # Create result
        result = PlanningResult(
            result_id=str(uuid.uuid4()),
            reasoning_result=reasoning_result,
            plan=plan,
            goal_tree=goal_tree,
            task_graph=task_graph,
            execution_graph=execution_graph,
            risk_analysis=risk_analysis,
            alternatives=alternatives,
            validation=validation,
            planning_duration=planning_duration,
            total_tasks=len(task_graph.tasks),
            total_goals=len(goal_tree.goals),
            estimated_duration=execution_graph.total_duration,
            execution_strategy=strategy
        )
        
        self.logger.info(
            f"Planning complete: {len(task_graph.tasks)} tasks, "
            f"{len(goal_tree.goals)} goals, "
            f"{planning_duration:.2f}s"
        )
        
        return result
    
    # =========================================================================
    # PIPELINE PHASES
    # =========================================================================
    
    async def _create_goals(
        self,
        reasoning_result: Dict[str, Any]
    ) -> GoalTree:
        """Create goals from reasoning result."""
        goal_tree = GoalTree()
        
        # Extract main goal
        main_goal_text = reasoning_result.get("answer", reasoning_result.get("conclusion", ""))
        
        if not main_goal_text:
            # Create default goal
            main_goal = self._goal_manager.create_goal(
                title="Execute Reasoning Result",
                description="Execute the reasoning process and achieve the conclusion",
                priority=GoalPriority.MEDIUM
            )
        else:
            main_goal = self._goal_manager.create_goal(
                title=main_goal_text[:100],
                description=main_goal_text,
                priority=GoalPriority.MEDIUM
            )
        
        goal_tree.add_goal(main_goal)
        
        # Extract sub-goals from reasoning steps
        steps = reasoning_result.get("reasoning_steps", [])
        
        if steps:
            sub_goals = []
            for i, step in enumerate(steps):
                step_text = step.get("step", f"Step {i+1}")
                sub_goal = self._goal_manager.create_goal(
                    title=step_text[:50],
                    description=step_text,
                    priority=GoalPriority.HIGH if i == 0 else GoalPriority.MEDIUM,
                    parent_id=main_goal.goal_id
                )
                sub_goals.append(sub_goal)
                goal_tree.add_goal(sub_goal)
        
        return goal_tree
    
    async def _decompose_tasks(
        self,
        goal_tree: GoalTree,
        reasoning_result: Dict[str, Any]
    ) -> TaskGraph:
        """Decompose goals into tasks."""
        task_graph = TaskGraph()
        
        for goal in goal_tree.goals.values():
            # Decompose each goal
            sub_graph = self._task_decomposer.decompose_goal(goal)
            
            # Merge into main graph
            for task_id, task in sub_graph.tasks.items():
                task_graph.add_task(task)
            
            for edge in sub_graph.edges:
                task_graph.add_edge(edge.source_id, edge.target_id)
        
        return task_graph
    
    def _build_execution_graph(
        self,
        task_graph: TaskGraph
    ) -> ExecutionGraph:
        """Build execution graph from task graph."""
        execution_graph = self._graph_planner.build_execution_graph(task_graph)
        return execution_graph
    
    async def _create_plan(
        self,
        goal_tree: GoalTree,
        task_graph: TaskGraph,
        execution_graph: ExecutionGraph,
        risk_analysis: RiskAnalysis,
        validation: PlanValidation,
        strategy: ExecutionStrategyType,
        alternatives: List[AlternativePlan],
        reasoning_result: Dict[str, Any]
    ) -> Plan:
        """Create final plan."""
        plan_id = str(uuid.uuid4())
        
        plan = Plan(
            plan_id=plan_id,
            title=reasoning_result.get("title", "Generated Plan"),
            description=reasoning_result.get("summary", ""),
            status=PlanStatus.VALIDATED if validation.is_valid else PlanStatus.DRAFT,
            goal_tree=goal_tree,
            task_graph=task_graph,
            execution_graph=execution_graph,
            risk_analysis=risk_analysis,
            alternatives=alternatives,
            validation=validation,
            estimated_duration=execution_graph.total_duration,
            execution_strategy=strategy
        )
        
        # Calculate metrics
        plan.estimated_cost = self._calculate_cost(task_graph)
        plan.confidence = self._calculate_confidence(validation, risk_analysis)
        
        return plan
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _calculate_cost(self, task_graph: TaskGraph) -> float:
        """Calculate estimated cost."""
        # Simple cost model: duration * base_rate
        total_duration = sum(
            t.estimated_duration for t in task_graph.tasks.values()
        )
        return total_duration * 0.01
    
    def _calculate_confidence(
        self,
        validation: PlanValidation,
        risk_analysis: RiskAnalysis
    ) -> float:
        """Calculate plan confidence."""
        base_confidence = 1.0
        
        # Reduce for validation issues
        if not validation.is_valid:
            base_confidence *= 0.5
        
        # Reduce for risk
        risk_penalty = risk_analysis.total_risk_score * 0.3
        base_confidence *= (1 - risk_penalty)
        
        return max(0.0, min(1.0, base_confidence))
    
    # =========================================================================
    # EXECUTION SUPPORT
    # =========================================================================
    
    async def execute_task(
        self,
        task_id: str,
        task_graph: TaskGraph
    ) -> bool:
        """Execute a single task (placeholder for actual execution)."""
        task = task_graph.tasks.get(task_id)
        if not task:
            return False
        
        task.start()
        
        # In real implementation, this would:
        # 1. Allocate resources
        # 2. Execute the task
        # 3. Handle results
        # 4. Release resources
        
        # For now, simulate completion
        task.complete()
        
        return True
    
    def track_progress(
        self,
        plan_id: str,
        task_graph: TaskGraph,
        start_time: datetime
    ) -> Any:
        """Track execution progress."""
        return self._progress_tracker.track(plan_id, task_graph, start_time)
    
    async def analyze_completion(
        self,
        plan_id: str,
        task_graph: TaskGraph,
        start_time: datetime,
        end_time: datetime
    ) -> CompletionAnalysis:
        """Analyze plan completion."""
        return self._completion_analyzer.analyze(
            plan_id, task_graph, start_time, end_time
        )
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "goal_manager": self._goal_manager.get_statistics(),
            "task_decomposer": self._task_decomposer.get_statistics(),
            "graph_planner": self._graph_planner.get_statistics(),
            "constraint_solver": self._constraint_solver.get_statistics(),
            "resource_planner": self._resource_planner.get_statistics(),
            "scheduler": self._scheduler.get_statistics(),
            "risk_analyzer": self._risk_analyzer.get_statistics(),
        }


# ============================================================================
# SINGLETON
# ============================================================================

_planning_engine_instance: Optional[PlanningEngine] = None


def get_planning_engine() -> PlanningEngine:
    """Get singleton instance of PlanningEngine."""
    global _planning_engine_instance
    if _planning_engine_instance is None:
        _planning_engine_instance = PlanningEngine()
    return _planning_engine_instance


async def initialize_planning_engine() -> PlanningEngine:
    """Initialize and get planning engine."""
    engine = get_planning_engine()
    await engine.initialize()
    return engine
