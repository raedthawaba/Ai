"""
Scheduler - Planning Engine v1.0
================================

Schedules task execution with priorities and parallelization.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from ..core.base import BaseComponent
from ..core.models import (
    Task, TaskStatus, TaskGraph, ExecutionGraph, ExecutionNode,
    ExecutionStrategyType
)


class Scheduler(BaseComponent):
    """
    Schedules task execution.
    
    Responsibilities:
    - Schedule tasks for execution
    - Handle priorities
    - Support parallel execution
    - Async scheduling
    """
    
    def __init__(self):
        super().__init__()
        self._scheduled_tasks: Dict[str, datetime] = {}
        self._execution_queue: List[str] = []
    
    async def _async_initialize(self) -> None:
        """Initialize the scheduler."""
        self.logger.info("Scheduler initialized")
    
    def schedule(
        self,
        task_graph: TaskGraph,
        execution_graph: ExecutionGraph,
        strategy: ExecutionStrategyType = ExecutionStrategyType.SEQUENTIAL,
        max_parallel: int = 5
    ) -> ExecutionGraph:
        """
        Schedule tasks for execution.
        
        Args:
            task_graph: Task graph
            execution_graph: Execution graph
            strategy: Execution strategy
            max_parallel: Maximum parallel tasks
            
        Returns:
            Scheduled execution graph
        """
        if strategy == ExecutionStrategyType.SEQUENTIAL:
            return self._schedule_sequential(task_graph, execution_graph)
        elif strategy == ExecutionStrategyType.PARALLEL:
            return self._schedule_parallel(task_graph, execution_graph, max_parallel)
        elif strategy == ExecutionStrategyType.PIPELINE:
            return self._schedule_pipeline(task_graph, execution_graph)
        elif strategy == ExecutionStrategyType.HYBRID:
            return self._schedule_hybrid(task_graph, execution_graph, max_parallel)
        else:
            return execution_graph
    
    def _schedule_sequential(
        self,
        task_graph: TaskGraph,
        execution_graph: ExecutionGraph
    ) -> ExecutionGraph:
        """Sequential scheduling."""
        order = task_graph.get_topological_order()
        
        current_time = execution_graph.start_time or datetime.utcnow()
        
        for i, task_id in enumerate(order):
            node = execution_graph.nodes.get(f"node_{i}")
            task = task_graph.tasks.get(task_id)
            
            if node and task:
                node.estimated_start = current_time
                node.estimated_end = current_time + timedelta(seconds=task.estimated_duration)
                
                self._scheduled_tasks[task_id] = current_time
                self._execution_queue.append(task_id)
                
                current_time = node.estimated_end
        
        return execution_graph
    
    def _schedule_parallel(
        self,
        task_graph: TaskGraph,
        execution_graph: ExecutionGraph,
        max_parallel: int
    ) -> ExecutionGraph:
        """Parallel scheduling."""
        order = task_graph.get_topological_order()
        current_time = execution_graph.start_time or datetime.utcnow()
        
        # Track running tasks
        running: List[tuple[str, datetime]] = []
        
        for task_id in order:
            task = task_graph.tasks.get(task_id)
            if not task:
                continue
            
            # Wait for dependencies
            while not self._can_start(task_id, task_graph, running):
                # Advance time to next task completion
                if running:
                    current_time = min(end for _, end in running)
                    running = [(tid, end) for tid, end in running if end > current_time]
                else:
                    break
            
            # Start this task
            start_time = current_time
            end_time = start_time + timedelta(seconds=task.estimated_duration)
            
            # Find node index
            node_idx = next(
                (i for i, n in execution_graph.nodes.items() if n.task_id == task_id),
                None
            )
            
            if node_idx:
                execution_graph.nodes[node_idx].estimated_start = start_time
                execution_graph.nodes[node_idx].estimated_end = end_time
            
            self._scheduled_tasks[task_id] = start_time
            
            # Manage parallel slots
            running.append((task_id, end_time))
            
            # Keep only max_parallel tasks
            if len(running) >= max_parallel:
                current_time = min(end for _, end in running)
                running = [(tid, end) for tid, end in running if end > current_time]
        
        return execution_graph
    
    def _schedule_pipeline(
        self,
        task_graph: TaskGraph,
        execution_graph: ExecutionGraph
    ) -> ExecutionGraph:
        """Pipeline scheduling (like assembly line)."""
        # Group tasks by stage
        stages = self._identify_stages(task_graph)
        
        current_time = execution_graph.start_time or datetime.utcnow()
        
        for stage_idx, stage_tasks in enumerate(stages):
            stage_start = current_time
            
            for task_id in stage_tasks:
                task = task_graph.tasks.get(task_id)
                if not task:
                    continue
                
                # All tasks in stage start at same time
                start_time = stage_start
                end_time = start_time + timedelta(seconds=task.estimated_duration)
                
                node_idx = next(
                    (i for i, n in execution_graph.nodes.items() if n.task_id == task_id),
                    None
                )
                
                if node_idx:
                    execution_graph.nodes[node_idx].estimated_start = start_time
                    execution_graph.nodes[node_idx].estimated_end = end_time
                
                self._scheduled_tasks[task_id] = start_time
            
            # Next stage starts after longest task in current stage
            stage_duration = max(
                task_graph.tasks[tid].estimated_duration
                for tid in stage_tasks
                if task_graph.tasks.get(tid)
            )
            current_time = stage_start + timedelta(seconds=stage_duration)
        
        return execution_graph
    
    def _schedule_hybrid(
        self,
        task_graph: TaskGraph,
        execution_graph: ExecutionGraph,
        max_parallel: int
    ) -> ExecutionGraph:
        """Hybrid scheduling (mix of sequential and parallel)."""
        # Identify critical path tasks (sequential)
        critical_tasks = self._identify_critical_path(task_graph)
        
        order = task_graph.get_topological_order()
        current_time = execution_graph.start_time or datetime.utcnow()
        
        running: List[tuple[str, datetime]] = []
        
        for task_id in order:
            task = task_graph.tasks.get(task_id)
            if not task:
                continue
            
            is_critical = task_id in critical_tasks
            
            if is_critical:
                # Sequential for critical path
                while running:
                    current_time = min(end for _, end in running)
                    running = [(tid, end) for tid, end in running if end > current_time]
                
                start_time = current_time
                end_time = start_time + timedelta(seconds=task.estimated_duration)
                
                self._scheduled_tasks[task_id] = start_time
                
                node_idx = next(
                    (i for i, n in execution_graph.nodes.items() if n.task_id == task_id),
                    None
                )
                
                if node_idx:
                    execution_graph.nodes[node_idx].estimated_start = start_time
                    execution_graph.nodes[node_idx].estimated_end = end_time
                
                current_time = end_time
            else:
                # Parallel for non-critical
                while not self._can_start(task_id, task_graph, running):
                    if running:
                        current_time = min(end for _, end in running)
                        running = [(tid, end) for tid, end in running if end > current_time]
                    else:
                        break
                
                start_time = current_time
                end_time = start_time + timedelta(seconds=task.estimated_duration)
                
                self._scheduled_tasks[task_id] = start_time
                
                node_idx = next(
                    (i for i, n in execution_graph.nodes.items() if n.task_id == task_id),
                    None
                )
                
                if node_idx:
                    execution_graph.nodes[node_idx].estimated_start = start_time
                    execution_graph.nodes[node_idx].estimated_end = end_time
                
                running.append((task_id, end_time))
                
                if len(running) >= max_parallel:
                    current_time = min(end for _, end in running)
                    running = [(tid, end) for tid, end in running if end > current_time]
        
        return execution_graph
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _can_start(
        self,
        task_id: str,
        task_graph: TaskGraph,
        running: List[tuple[str, datetime]]
    ) -> bool:
        """Check if task can start (all dependencies complete or running)."""
        task = task_graph.tasks.get(task_id)
        if not task:
            return False
        
        for dep_id in task.dependencies:
            dep_task = task_graph.tasks.get(dep_id)
            if not dep_task:
                continue
            
            if dep_task.status != TaskStatus.COMPLETED:
                # Check if dependency is still running
                if not any(tid == dep_id for tid, _ in running):
                    return False
        
        return True
    
    def _identify_stages(self, task_graph: TaskGraph) -> List[List[str]]:
        """Identify execution stages (levels in dependency graph)."""
        in_degree = {tid: 0 for tid in task_graph.tasks}
        
        for task in task_graph.tasks.values():
            for dep in task.dependencies:
                if dep in in_degree:
                    in_degree[task.task_id] += 1
        
        stages = []
        processed = set()
        
        while len(processed) < len(task_graph.tasks):
            # Find tasks with no remaining dependencies
            current_stage = [
                tid for tid, deg in in_degree.items()
                if deg == 0 and tid not in processed
            ]
            
            if not current_stage:
                break
            
            stages.append(current_stage)
            processed.update(current_stage)
            
            # Update in-degrees
            for task_id in current_stage:
                task = task_graph.tasks.get(task_id)
                if task:
                    for dependent_id in task.dependents:
                        if dependent_id in in_degree:
                            in_degree[dependent_id] -= 1
        
        return stages
    
    def _identify_critical_path(self, task_graph: TaskGraph) -> Set[str]:
        """Identify critical path tasks."""
        # Simplified: return tasks with most dependents
        critical = set()
        
        for task in task_graph.tasks.values():
            if len(task.dependents) > 1:
                critical.add(task.task_id)
        
        return critical
    
    def get_next_task(self) -> Optional[str]:
        """Get the next task to execute."""
        if not self._execution_queue:
            return None
        
        return self._execution_queue.pop(0)
    
    def get_scheduled_time(self, task_id: str) -> Optional[datetime]:
        """Get scheduled time for a task."""
        return self._scheduled_tasks.get(task_id)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        return {
            "scheduled_tasks": len(self._scheduled_tasks),
            "queue_length": len(self._execution_queue)
        }


_scheduler_instance: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get singleton instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = Scheduler()
    return _scheduler_instance
