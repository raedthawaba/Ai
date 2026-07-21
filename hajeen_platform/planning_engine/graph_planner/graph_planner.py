"""
Graph Planner - Planning Engine v1.0
====================================

Builds and optimizes the execution DAG.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.base import BaseComponent, PlanningContext
from ..core.models import (
    Task, TaskStatus, TaskGraph, TaskDependency,
    ExecutionNode, ExecutionGraph,
    Resource, ResourceAllocation
)


class GraphPlanner(BaseComponent):
    """
    Builds and optimizes the execution graph.
    
    Responsibilities:
    - Create execution graph from task graph
    - Optimize task ordering
    - Calculate critical path
    - Determine scheduling
    """
    
    def __init__(self):
        super().__init__()
        self._optimization_enabled = True
        self._critical_path_cache: Optional[List[str]] = None
    
    async def _async_initialize(self) -> None:
        """Initialize the graph planner."""
        self.logger.info("GraphPlanner initialized")
    
    # =========================================================================
    # GRAPH BUILDING
    # =========================================================================
    
    def build_execution_graph(
        self,
        task_graph: TaskGraph,
        start_time: Optional[datetime] = None,
        resources: Optional[Dict[str, Resource]] = None
    ) -> ExecutionGraph:
        """
        Build execution graph from task graph.
        
        Args:
            task_graph: Input task graph
            start_time: Planned start time
            resources: Available resources
            
        Returns:
            ExecutionGraph with scheduling
        """
        if task_graph.has_cycle():
            raise ValueError("Cannot build execution graph: task graph contains cycles")
        
        resources = resources or {}
        execution_graph = ExecutionGraph(
            graph_id=str(uuid.uuid4()),
            plan_id="",
            start_time=start_time or datetime.utcnow()
        )
        
        # Get topological order
        order = task_graph.get_topological_order()
        
        # Calculate earliest start times
        earliest_starts = self._calculate_earliest_starts(task_graph, order, start_time)
        
        # Create execution nodes
        current_time = start_time or datetime.utcnow()
        
        for i, task_id in enumerate(order):
            task = task_graph.tasks[task_id]
            
            node = ExecutionNode(
                node_id=f"node_{i}",
                task_id=task_id,
                execution_order=i,
                estimated_start=earliest_starts.get(task_id, current_time),
                estimated_end=earliest_starts.get(task_id, current_time) + 
                              timedelta(seconds=task.estimated_duration),
                status=TaskStatus.PENDING
            )
            
            execution_graph.add_node(node)
        
        # Add edges
        for task_id in order:
            task = task_graph.tasks[task_id]
            for dep_id in task.dependencies:
                execution_graph.edges.append((dep_id, task_id))
        
        # Calculate total duration
        execution_graph.total_duration = self._calculate_total_duration(
            execution_graph, task_graph
        )
        
        self.logger.info(
            f"Built execution graph: {len(execution_graph.nodes)} nodes, "
            f"{len(execution_graph.edges)} edges"
        )
        
        return execution_graph
    
    def _calculate_earliest_starts(
        self,
        task_graph: TaskGraph,
        order: List[str],
        start_time: Optional[datetime]
    ) -> Dict[str, datetime]:
        """Calculate earliest start time for each task."""
        start = start_time or datetime.utcnow()
        earliest_starts = {}
        
        for task_id in order:
            task = task_graph.tasks[task_id]
            
            if not task.dependencies:
                earliest_starts[task_id] = start
                continue
            
            # Start after all dependencies complete
            max_end = start
            for dep_id in task.dependencies:
                dep_task = task_graph.tasks.get(dep_id)
                if not dep_task:
                    continue
                
                dep_end = earliest_starts.get(dep_id, start) + \
                         timedelta(seconds=dep_task.estimated_duration)
                max_end = max(max_end, dep_end)
            
            earliest_starts[task_id] = max_end
        
        return earliest_starts
    
    def _calculate_total_duration(
        self,
        execution_graph: ExecutionGraph,
        task_graph: TaskGraph
    ) -> float:
        """Calculate total execution duration."""
        if not execution_graph.nodes:
            return 0.0
        
        max_duration = 0.0
        
        for node in execution_graph.nodes.values():
            if node.estimated_end and node.estimated_start:
                duration = (node.estimated_end - node.estimated_start).total_seconds()
                max_duration = max(max_duration, duration)
        
        return max_duration
    
    # =========================================================================
    # CRITICAL PATH
    # =========================================================================
    
    def find_critical_path(
        self,
        execution_graph: ExecutionGraph,
        task_graph: TaskGraph
    ) -> List[str]:
        """
        Find the critical path through the execution graph.
        
        Returns:
            List of task IDs on the critical path
        """
        if self._critical_path_cache:
            return self._critical_path_cache
        
        # Calculate earliest and latest start/finish times
        nodes = list(execution_graph.nodes.values())
        nodes.sort(key=lambda n: n.execution_order)
        
        # Forward pass: calculate earliest times
        earliest_start = {}
        earliest_finish = {}
        
        for node in nodes:
            task = task_graph.tasks.get(node.task_id)
            if not task:
                continue
            
            if not node.estimated_start:
                continue
            
            earliest_start[node.task_id] = node.estimated_start
            earliest_finish[node.task_id] = node.estimated_end
        
        # Backward pass: calculate latest times
        latest_start = {}
        latest_finish = {}
        
        total_finish = max(earliest_finish.values()) if earliest_finish else datetime.utcnow()
        
        for node in reversed(nodes):
            task = task_graph.tasks.get(node.task_id)
            if not task:
                continue
            
            if node.estimated_end:
                latest_finish[node.task_id] = node.estimated_end
            else:
                latest_finish[node.task_id] = total_finish
            
            duration = task.estimated_duration
            latest_start[node.task_id] = latest_finish[node.task_id] - timedelta(seconds=duration)
        
        # Find critical path: tasks with zero slack
        critical_path = []
        for node in nodes:
            es = earliest_start.get(node.task_id)
            ls = latest_start.get(node.task_id)
            
            if es and ls:
                slack = (ls - es).total_seconds()
                if abs(slack) < 1:  # Less than 1 second slack
                    critical_path.append(node.task_id)
        
        self._critical_path_cache = critical_path
        return critical_path
    
    # =========================================================================
    # OPTIMIZATION
    # =========================================================================
    
    def optimize_order(self, task_graph: TaskGraph) -> TaskGraph:
        """
        Optimize task ordering for efficiency.
        
        Args:
            task_graph: Input task graph
            
        Returns:
            Optimized task graph
        """
        if not self._optimization_enabled:
            return task_graph
        
        # Topological sort with priority consideration
        tasks = list(task_graph.tasks.values())
        
        # Sort by: dependencies first, then priority
        tasks.sort(key=lambda t: (
            len(t.dependencies),  # Fewer dependencies first
            -t.priority  # Higher priority (lower number) first
        ))
        
        # Rebuild edges maintaining dependency order
        new_graph = TaskGraph()
        
        # Add tasks in new order
        for task in tasks:
            new_graph.add_task(task)
        
        # Add edges
        for edge in task_graph.edges:
            new_graph.add_edge(edge.source_id, edge.target_id)
        
        self.logger.info("Optimized task graph order")
        return new_graph
    
    def identify_parallel_opportunities(
        self,
        task_graph: TaskGraph
    ) -> List[Set[str]]:
        """
        Identify groups of tasks that can run in parallel.
        
        Returns:
            List of task ID sets that can run in parallel
        """
        parallel_groups = []
        processed = set()
        
        # Find tasks with no dependencies
        ready_tasks = [
            tid for tid, task in task_graph.tasks.items()
            if not task.dependencies and task.status == TaskStatus.PENDING
        ]
        
        if ready_tasks:
            parallel_groups.append(set(ready_tasks))
            processed.update(ready_tasks)
        
        # Find subsequent parallel opportunities
        while len(processed) < len(task_graph.tasks):
            # Find next batch of tasks whose dependencies are all in processed
            next_ready = []
            
            for tid, task in task_graph.tasks.items():
                if tid in processed or task.status != TaskStatus.PENDING:
                    continue
                
                deps_satisfied = all(
                    dep_id in processed or 
                    task_graph.tasks.get(dep_id, Task(task_id="", title="")).status == TaskStatus.COMPLETED
                    for dep_id in task.dependencies
                )
                
                if deps_satisfied:
                    next_ready.append(tid)
            
            if not next_ready:
                break
            
            # Check which can run in parallel
            parallel_batch = []
            for tid in next_ready:
                can_run = True
                for other_tid in parallel_batch:
                    if self._has_resource_conflict(task_graph.tasks[tid], task_graph.tasks[other_tid]):
                        can_run = False
                        break
                
                if can_run:
                    parallel_batch.append(tid)
            
            if parallel_batch:
                parallel_groups.append(set(parallel_batch))
                processed.update(parallel_batch)
            else:
                # If no parallel batch, add one task and continue
                parallel_groups.append({next_ready[0]})
                processed.add(next_ready[0])
        
        return parallel_groups
    
    def _has_resource_conflict(self, task1: Task, task2: Task) -> bool:
        """Check if two tasks have conflicting resource requirements."""
        r1 = {(r.type, r.name) for r in task1.required_resources}
        r2 = {(r.type, r.name) for r in task2.required_resources}
        
        # Non-shareable resources conflict
        non_shareable = {ResourceType.MEMORY, ResourceType.STORAGE}
        
        for r in r1 & r2:
            if r[0] in non_shareable:
                return True
        
        return False
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def validate_graph(self, task_graph: TaskGraph) -> Tuple[bool, List[str]]:
        """
        Validate the task graph.
        
        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues = []
        
        # Check for cycles
        if task_graph.has_cycle():
            issues.append("Task graph contains circular dependencies")
        
        # Check for missing dependencies
        for task_id, task in task_graph.tasks.items():
            for dep_id in task.dependencies:
                if dep_id not in task_graph.tasks:
                    issues.append(f"Task {task_id} depends on missing task {dep_id}")
        
        # Check for self-dependency
        for task_id, task in task_graph.tasks.items():
            if task_id in task.dependencies:
                issues.append(f"Task {task_id} has self-dependency")
        
        # Check for unreachable tasks
        reachable = self._find_reachable_tasks(task_graph)
        for task_id in task_graph.tasks:
            if task_id not in reachable:
                issues.append(f"Task {task_id} is not reachable from any start node")
        
        return len(issues) == 0, issues
    
    def _find_reachable_tasks(self, task_graph: TaskGraph) -> Set[str]:
        """Find all tasks reachable from start nodes."""
        reachable = set()
        queue = []
        
        # Find start nodes (no incoming edges)
        for task_id, task in task_graph.tasks.items():
            if not task.dependencies:
                queue.append(task_id)
        
        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            
            reachable.add(current)
            
            # Add dependents
            for task_id, task in task_graph.tasks.items():
                if current in task.dependencies and task_id not in reachable:
                    queue.append(task_id)
        
        return reachable
    
    # =========================================================================
    # SCHEDULING
    # =========================================================================
    
    def schedule(
        self,
        execution_graph: ExecutionGraph,
        task_graph: TaskGraph,
        strategy: str = "earliest_first"
    ) -> ExecutionGraph:
        """
        Apply scheduling strategy to execution graph.
        
        Args:
            execution_graph: Execution graph to schedule
            task_graph: Underlying task graph
            strategy: Scheduling strategy
            
        Returns:
            Scheduled execution graph
        """
        if strategy == "earliest_first":
            return self._schedule_earliest_first(execution_graph, task_graph)
        elif strategy == "priority_first":
            return self._schedule_priority_first(execution_graph, task_graph)
        elif strategy == "critical_path":
            return self._schedule_critical_path_first(execution_graph, task_graph)
        else:
            return execution_graph
    
    def _schedule_earliest_first(
        self,
        execution_graph: ExecutionGraph,
        task_graph: TaskGraph
    ) -> ExecutionGraph:
        """Schedule by earliest start time."""
        # Already in topological order from build_execution_graph
        return execution_graph
    
    def _schedule_priority_first(
        self,
        execution_graph: ExecutionGraph,
        task_graph: TaskGraph
    ) -> ExecutionGraph:
        """Schedule by task priority."""
        # Resort by priority
        nodes = list(execution_graph.nodes.values())
        nodes.sort(key=lambda n: task_graph.tasks.get(n.task_id, Task(task_id="", title="")).priority)
        
        # Update execution order
        for i, node in enumerate(nodes):
            node.execution_order = i
        
        return execution_graph
    
    def _schedule_critical_path_first(
        self,
        execution_graph: ExecutionGraph,
        task_graph: TaskGraph
    ) -> ExecutionGraph:
        """Schedule critical path tasks first."""
        critical = set(self.find_critical_path(execution_graph, task_graph))
        
        # Separate critical and non-critical
        critical_nodes = []
        non_critical_nodes = []
        
        for node in execution_graph.nodes.values():
            if node.task_id in critical:
                critical_nodes.append(node)
            else:
                non_critical_nodes.append(node)
        
        # Reorder: critical first
        critical_nodes.sort(key=lambda n: n.execution_order)
        non_critical_nodes.sort(key=lambda n: n.execution_order)
        
        all_nodes = critical_nodes + non_critical_nodes
        
        # Rebuild graph with new order
        new_graph = ExecutionGraph(
            graph_id=execution_graph.graph_id,
            plan_id=execution_graph.plan_id,
            start_time=execution_graph.start_time,
            end_time=execution_graph.end_time,
            total_duration=execution_graph.total_duration
        )
        
        for i, node in enumerate(all_nodes):
            node.execution_order = i
            new_graph.add_node(node)
        
        for edge in execution_graph.edges:
            new_graph.edges.append(edge)
        
        return new_graph
    
    # =========================================================================
    # METRICS
    # =========================================================================
    
    def get_statistics(
        self,
        task_graph: TaskGraph,
        execution_graph: Optional[ExecutionGraph] = None
    ) -> Dict[str, Any]:
        """Get graph statistics."""
        stats = {
            "total_tasks": len(task_graph.tasks),
            "total_edges": len(task_graph.edges),
            "has_cycles": task_graph.has_cycle(),
            "parallel_opportunities": len(self.identify_parallel_opportunities(task_graph))
        }
        
        if execution_graph:
            stats.update({
                "total_duration": execution_graph.total_duration,
                "total_nodes": len(execution_graph.nodes),
                "critical_path_length": len(self.find_critical_path(execution_graph, task_graph))
            })
        
        return stats


# ============================================================================
# SINGLETON ACCESSOR
# ============================================================================

_graph_planner_instance: Optional[GraphPlanner] = None


def get_graph_planner() -> GraphPlanner:
    """Get singleton instance of GraphPlanner."""
    global _graph_planner_instance
    if _graph_planner_instance is None:
        _graph_planner_instance = GraphPlanner()
    return _graph_planner_instance
