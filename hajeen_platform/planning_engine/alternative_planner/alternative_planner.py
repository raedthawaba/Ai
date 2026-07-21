"""
Alternative Planner, Plan Validator, Execution Strategy, Replanning Engine,
Progress Tracker, Completion Analyzer - Planning Engine v1.0
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..core.base import BaseComponent
from ..core.models import (
    Task, TaskGraph, TaskStatus, Plan, PlanValidation, AlternativePlan,
    ExecutionStrategyType, RiskAnalysis, Risk, RiskLevel,
    ProgressSnapshot, CompletionAnalysis, ExecutionGraph, GoalTree
)


# ============================================================================
# ALTERNATIVE PLANNER
# ============================================================================

class AlternativePlanner(BaseComponent):
    """
    Generates and evaluates alternative plans.
    """
    
    async def _async_initialize(self) -> None:
        self.logger.info("AlternativePlanner initialized")
    
    def generate_alternatives(
        self,
        primary_graph: TaskGraph,
        count: int = 3
    ) -> List[AlternativePlan]:
        """Generate alternative plans."""
        alternatives = []
        
        for i in range(count):
            alt = AlternativePlan(
                plan_id=f"alt_{i}_{str(uuid.uuid4())[:8]}",
                title=f"Alternative {i+1}",
                description=f"Alternative approach {i+1}"
            )
            
            # Vary parameters
            if i == 0:
                alt.estimated_duration = self._optimize_for_speed(primary_graph)
            elif i == 1:
                alt.estimated_duration = self._optimize_for_cost(primary_graph)
            else:
                alt.estimated_duration = self._balance(primary_graph)
            
            alt.success_probability = 0.7 + (i * 0.1)
            alt.risk_score = 0.3 - (i * 0.05)
            
            alternatives.append(alt)
        
        return alternatives
    
    def _optimize_for_speed(self, graph: TaskGraph) -> float:
        return sum(t.estimated_duration for t in graph.tasks.values()) * 0.7
    
    def _optimize_for_cost(self, graph: TaskGraph) -> float:
        return sum(t.estimated_duration for t in graph.tasks.values()) * 0.9
    
    def _balance(self, graph: TaskGraph) -> float:
        return sum(t.estimated_duration for t in graph.tasks.values()) * 0.8
    
    def compare_alternatives(
        self,
        alternatives: List[AlternativePlan]
    ) -> List[AlternativePlan]:
        """Compare and rank alternatives."""
        for alt in alternatives:
            # Simple scoring
            score = (
                alt.success_probability * 0.4 +
                (1 - alt.risk_score) * 0.3 +
                (1 - alt.estimated_cost / 1000) * 0.2 +
                (1 - alt.estimated_duration / 3600) * 0.1
            )
            alt.rank = int(score * 100)
        
        return sorted(alternatives, key=lambda a: a.rank, reverse=True)


# ============================================================================
# PLAN VALIDATOR
# ============================================================================

class PlanValidator(BaseComponent):
    """
    Validates execution plans.
    """
    
    async def _async_initialize(self) -> None:
        self.logger.info("PlanValidator initialized")
    
    def validate(
        self,
        task_graph: TaskGraph,
        execution_graph: Optional[ExecutionGraph] = None
    ) -> PlanValidation:
        """Validate a plan."""
        validation = PlanValidation(is_valid=True)
        
        # Check for cycles
        if task_graph.has_cycle():
            validation.is_valid = False
            validation.circular_dependencies.append("Task graph contains cycles")
        
        # Check for missing dependencies
        for task in task_graph.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in task_graph.tasks:
                    validation.missing_tasks.append(f"{task.task_id} -> {dep_id}")
        
        # Check for unreachable tasks
        reachable = self._find_reachable(task_graph)
        for task_id in task_graph.tasks:
            if task_id not in reachable:
                validation.warnings.append(f"Unreachable task: {task_id}")
        
        return validation
    
    def _find_reachable(self, task_graph: TaskGraph) -> set:
        reachable = set()
        queue = [tid for tid, t in task_graph.tasks.items() if not t.dependencies]
        
        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            reachable.add(current)
            
            for tid, t in task_graph.tasks.items():
                if current in t.dependencies and tid not in reachable:
                    queue.append(tid)
        
        return reachable


# ============================================================================
# EXECUTION STRATEGY SELECTOR
# ============================================================================

class ExecutionStrategySelector(BaseComponent):
    """
    Selects optimal execution strategy.
    """
    
    async def _async_initialize(self) -> None:
        self.logger.info("ExecutionStrategySelector initialized")
    
    def select(
        self,
        task_graph: TaskGraph,
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionStrategyType:
        """Select best execution strategy."""
        context = context or {}
        
        parallel_tasks = sum(1 for t in task_graph.tasks.values() if not t.dependencies)
        total_tasks = len(task_graph.tasks)
        
        # Decision logic
        if parallel_tasks >= total_tasks * 0.5:
            return ExecutionStrategyType.PARALLEL
        elif context.get("pipeline_stages", 0) > 1:
            return ExecutionStrategyType.PIPELINE
        elif context.get("use_hybrid", False):
            return ExecutionStrategyType.HYBRID
        else:
            return ExecutionStrategyType.SEQUENTIAL


# ============================================================================
# REPLANNING ENGINE
# ============================================================================

class ReplanningEngine(BaseComponent):
    """
    Handles plan modifications during execution.
    """
    
    async def _async_initialize(self) -> None:
        self.logger.info("ReplanningEngine initialized")
    
    def handle_failure(
        self,
        task_id: str,
        task_graph: TaskGraph,
        error: str
    ) -> Tuple[bool, TaskGraph]:
        """
        Handle task failure by replanning.
        
        Returns:
            Tuple of (replanning_needed, updated_graph)
        """
        task = task_graph.tasks.get(task_id)
        if not task:
            return False, task_graph
        
        # Mark task as failed
        task.status = TaskStatus.FAILED
        task.error = error
        
        # Check if plan can continue
        # For now, simple approach - mark dependents as blocked
        for dependent_id in task.dependents:
            dependent = task_graph.tasks.get(dependent_id)
            if dependent and dependent.status == TaskStatus.READY:
                dependent.status = TaskStatus.BLOCKED
        
        return True, task_graph
    
    def reorder_tasks(
        self,
        task_graph: TaskGraph,
        priority_updates: Dict[str, int]
    ) -> TaskGraph:
        """Reorder tasks based on new priorities."""
        for task_id, new_priority in priority_updates.items():
            task = task_graph.tasks.get(task_id)
            if task:
                task.priority = new_priority
        
        return task_graph


# ============================================================================
# PROGRESS TRACKER
# ============================================================================

class ProgressTracker(BaseComponent):
    """
    Tracks execution progress.
    """
    
    def __init__(self):
        super().__init__()
        self._snapshots: List[ProgressSnapshot] = []
    
    async def _async_initialize(self) -> None:
        self.logger.info("ProgressTracker initialized")
    
    def track(
        self,
        plan_id: str,
        task_graph: TaskGraph,
        start_time: datetime
    ) -> ProgressSnapshot:
        """Track current progress."""
        completed = sum(
            1 for t in task_graph.tasks.values()
            if t.status == TaskStatus.COMPLETED
        )
        failed = sum(
            1 for t in task_graph.tasks.values()
            if t.status == TaskStatus.FAILED
        )
        running = sum(
            1 for t in task_graph.tasks.values()
            if t.status == TaskStatus.RUNNING
        )
        
        total = len(task_graph.tasks)
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Estimate remaining
        if completed > 0:
            avg_task_time = elapsed / completed
            remaining = total - completed - failed
            estimated_remaining = remaining * avg_task_time
        else:
            estimated_remaining = 0
        
        snapshot = ProgressSnapshot(
            plan_id=plan_id,
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=failed,
            running_tasks=running,
            pending_tasks=total - completed - failed - running,
            elapsed_time=elapsed,
            estimated_remaining=estimated_remaining,
            eta=datetime.utcnow() + timedelta(seconds=estimated_remaining) if estimated_remaining > 0 else None,
            progress_percentage=(completed / total * 100) if total > 0 else 0
        )
        
        self._snapshots.append(snapshot)
        return snapshot
    
    def get_latest_snapshot(self, plan_id: str) -> Optional[ProgressSnapshot]:
        """Get latest progress snapshot for a plan."""
        plan_snapshots = [s for s in self._snapshots if s.plan_id == plan_id]
        return plan_snapshots[-1] if plan_snapshots else None


# ============================================================================
# COMPLETION ANALYZER
# ============================================================================

class CompletionAnalyzer(BaseComponent):
    """
    Analyzes plan completion and extracts lessons.
    """
    
    async def _async_initialize(self) -> None:
        self.logger.info("CompletionAnalyzer initialized")
    
    def analyze(
        self,
        plan_id: str,
        task_graph: TaskGraph,
        start_time: datetime,
        end_time: datetime
    ) -> CompletionAnalysis:
        """Analyze plan completion."""
        completed = sum(
            1 for t in task_graph.tasks.values()
            if t.status == TaskStatus.COMPLETED
        )
        failed = sum(
            1 for t in task_graph.tasks.values()
            if t.status == TaskStatus.FAILED
        )
        
        total = len(task_graph.tasks)
        duration = (end_time - start_time).total_seconds()
        
        # Calculate accuracy (estimated vs actual)
        estimated = sum(t.estimated_duration for t in task_graph.tasks.values())
        accuracy = min(1.0, estimated / duration) if duration > 0 else 0
        
        analysis = CompletionAnalysis(
            plan_id=plan_id,
            success=failed == 0,
            total_duration=duration,
            estimated_duration=estimated,
            accuracy=accuracy,
            tasks_completed=completed,
            tasks_failed=failed,
            tasks_skipped=sum(
                1 for t in task_graph.tasks.values()
                if t.status == TaskStatus.SKIPPED
            )
        )
        
        # Generate insights
        if failed == 0:
            analysis.success_factors.append("All tasks completed successfully")
        else:
            analysis.failure_factors.append(f"{failed} tasks failed")
        
        if accuracy > 0.9:
            analysis.success_factors.append("Duration estimates were accurate")
        else:
            analysis.improvements.append("Improve duration estimation")
        
        return analysis


# ============================================================================
# SINGLETON INSTANCES
# ============================================================================

_alt_planner: Optional[AlternativePlanner] = None
_validator: Optional[PlanValidator] = None
_strategy_sel: Optional[ExecutionStrategySelector] = None
_replanner: Optional[ReplanningEngine] = None
_tracker: Optional[ProgressTracker] = None
_analyzer: Optional[CompletionAnalyzer] = None


def get_alternative_planner() -> AlternativePlanner:
    global _alt_planner
    if _alt_planner is None:
        _alt_planner = AlternativePlanner()
    return _alt_planner


def get_plan_validator() -> PlanValidator:
    global _validator
    if _validator is None:
        _validator = PlanValidator()
    return _validator


def get_execution_strategy_selector() -> ExecutionStrategySelector:
    global _strategy_sel
    if _strategy_sel is None:
        _strategy_sel = ExecutionStrategySelector()
    return _strategy_sel


def get_replanning_engine() -> ReplanningEngine:
    global _replanner
    if _replanner is None:
        _replanner = ReplanningEngine()
    return _replanner


def get_progress_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProgressTracker()
    return _tracker


def get_completion_analyzer() -> CompletionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = CompletionAnalyzer()
    return _analyzer
