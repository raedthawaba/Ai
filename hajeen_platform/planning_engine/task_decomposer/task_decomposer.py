"""
Task Decomposer - Planning Engine v1.0
======================================

Converts goals into executable tasks with dependency detection.
"""

from __future__ import annotations

import uuid
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.base import BaseComponent, PlanningContext
from ..core.models import (
    Task, TaskStatus, TaskType, TaskGraph, TaskDependency,
    Goal, GoalPriority, Resource, ResourceType
)


class TaskDecomposer(BaseComponent):
    """
    Decomposes goals into executable tasks.
    
    Responsibilities:
    - Convert goals to tasks
    - Detect dependencies between tasks
    - Identify parallelizable tasks
    - Recursive decomposition
    - Task prioritization
    """
    
    def __init__(self):
        super().__init__()
        self._task_templates: Dict[str, Dict[str, Any]] = {}
        self._decomposition_rules: List[Dict[str, Any]] = []
        self._decomposed_count = 0
    
    async def _async_initialize(self) -> None:
        """Initialize the task decomposer."""
        self._initialize_templates()
        self._initialize_rules()
        self.logger.info("TaskDecomposer initialized")
    
    def _initialize_templates(self) -> None:
        """Initialize common task templates."""
        self._task_templates = {
            "research": {
                "type": TaskType.QUERY,
                "duration_factor": 1.5,
                "resources": [ResourceType.COMPUTE, ResourceType.NETWORK]
            },
            "analysis": {
                "type": TaskType.ANALYSIS,
                "duration_factor": 1.2,
                "resources": [ResourceType.COMPUTE]
            },
            "verification": {
                "type": TaskType.VERIFICATION,
                "duration_factor": 1.0,
                "resources": [ResourceType.COMPUTE]
            },
            "synthesis": {
                "type": TaskType.SYNTHESIS,
                "duration_factor": 1.3,
                "resources": [ResourceType.COMPUTE, ResourceType.MEMORY]
            },
            "decision": {
                "type": TaskType.DECISION,
                "duration_factor": 0.8,
                "resources": [ResourceType.COMPUTE]
            }
        }
    
    def _initialize_rules(self) -> None:
        """Initialize decomposition rules."""
        self._decomposition_rules = [
            {
                "name": "sequential_decomposition",
                "pattern": r"(first|then|next|after|before)",
                "action": "sequential"
            },
            {
                "name": "parallel_decomposition",
                "pattern": r"(and|同时|simultaneously|together)",
                "action": "parallel"
            },
            {
                "name": "conditional_decomposition",
                "pattern": r"(if|when|unless|depending)",
                "action": "conditional"
            },
            {
                "name": "iterative_decomposition",
                "pattern": r"(each|every|repeat|loop)",
                "action": "loop"
            }
        ]
    
    # =========================================================================
    # DECOMPOSITION METHODS
    # =========================================================================
    
    def decompose_goal(
        self,
        goal: Goal,
        max_depth: int = 3,
        current_depth: int = 0
    ) -> TaskGraph:
        """
        Decompose a goal into a task graph.
        
        Args:
            goal: Goal to decompose
            max_depth: Maximum recursion depth
            current_depth: Current recursion depth
            
        Returns:
            TaskGraph with all decomposed tasks
        """
        graph = TaskGraph()
        
        # Create main task for goal
        main_task = self._create_task_from_goal(goal, is_root=True)
        graph.add_task(main_task)
        
        # Decompose based on goal metadata
        if current_depth < max_depth:
            sub_tasks = self._decompose_based_on_type(goal, main_task)
            
            for sub_task in sub_tasks:
                graph.add_task(sub_task)
                
                # Add dependency
                graph.add_edge(main_task.task_id, sub_task.task_id)
                
                # Recursive decomposition for sub-goals
                if hasattr(goal, 'child_ids') and goal.child_ids:
                    # Continue recursion
                    pass
        
        # Detect dependencies
        self._detect_dependencies(graph)
        
        # Mark parallelizable tasks
        self._mark_parallel_tasks(graph)
        
        self._decomposed_count += 1
        self.record_metric("goals_decomposed", self._decomposed_count)
        
        self.logger.info(f"Decomposed goal {goal.goal_id} into {len(graph.tasks)} tasks")
        return graph
    
    def decompose_text(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Task]:
        """
        Decompose a text description into tasks.
        
        Args:
            text: Text description of tasks
            context: Additional context
            
        Returns:
            List of decomposed tasks
        """
        tasks = []
        context = context or {}
        
        # Split text into sentences/phrases
        segments = self._split_text_segments(text)
        
        current_order = 0
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            # Detect execution mode
            execution_mode, segment = self._detect_execution_mode(segment)
            
            # Create task
            task = Task(
                task_id=str(uuid.uuid4()),
                title=self._extract_title(segment),
                description=segment,
                task_type=self._detect_task_type(segment),
                execution_mode=execution_mode,
                estimated_duration=self._estimate_duration(segment),
                priority=self._calculate_priority(segment, context),
                order=current_order
            )
            
            tasks.append(task)
            current_order += 1
        
        # Detect dependencies from text
        self._detect_text_dependencies(tasks)
        
        return tasks
    
    def decompose_recursively(
        self,
        goal: Goal,
        task_definitions: List[Dict[str, Any]],
        max_depth: int = 3,
        current_depth: int = 0
    ) -> TaskGraph:
        """
        Recursively decompose a goal with detailed task definitions.
        
        Args:
            goal: Parent goal
            task_definitions: List of task definitions
            max_depth: Maximum recursion depth
            current_depth: Current depth
            
        Returns:
            Complete task graph
        """
        graph = TaskGraph()
        
        parent_task = self._create_task_from_goal(goal, is_root=True)
        graph.add_task(parent_task)
        
        for i, td in enumerate(task_definitions):
            # Create task
            task = self._create_task_from_definition(td, goal.goal_id, i)
            graph.add_task(task)
            
            # Add dependency to parent
            graph.add_edge(parent_task.task_id, task.task_id)
            
            # Recursive decomposition
            if current_depth < max_depth and "sub_tasks" in td:
                sub_graph = self.decompose_recursively(
                    goal=Goal(
                        goal_id=task.task_id,
                        title=task.title,
                        description=task.description
                    ),
                    task_definitions=td["sub_tasks"],
                    max_depth=max_depth,
                    current_depth=current_depth + 1
                )
                
                # Merge sub-graph
                for sub_task_id, sub_task in sub_graph.tasks.items():
                    graph.add_task(sub_task)
                for edge in sub_graph.edges:
                    graph.add_edge(edge.source_id, edge.target_id)
        
        # Detect additional dependencies
        self._detect_dependencies(graph)
        
        return graph
    
    # =========================================================================
    # TASK CREATION HELPERS
    # =========================================================================
    
    def _create_task_from_goal(self, goal: Goal, is_root: bool = False) -> Task:
        """Create a task from a goal."""
        return Task(
            task_id=f"{goal.goal_id}_task",
            title=goal.title,
            description=goal.description,
            task_type=TaskType.ACTION,
            status=TaskStatus.PENDING,
            estimated_duration=self._estimate_from_goal(goal),
            priority=self._priority_to_int(goal.priority),
            input_data={"goal_id": goal.goal_id},
            metadata=goal.metadata
        )
    
    def _create_task_from_definition(
        self,
        definition: Dict[str, Any],
        parent_id: str,
        index: int
    ) -> Task:
        """Create a task from a definition dict."""
        return Task(
            task_id=f"{parent_id}_subtask_{index}",
            title=definition.get("title", f"Task {index}"),
            description=definition.get("description", ""),
            task_type=TaskType(definition.get("type", "action")),
            status=TaskStatus.PENDING,
            estimated_duration=definition.get("duration", 60.0),
            priority=definition.get("priority", 5),
            input_data=definition.get("input", {}),
            dependencies=definition.get("depends_on", [])
        )
    
    def _decompose_based_on_type(self, goal: Goal, parent_task: Task) -> List[Task]:
        """Decompose based on goal type or metadata."""
        tasks = []
        
        # Check for explicit sub-goals
        if hasattr(goal, 'child_ids') and goal.child_ids:
            for child_id in goal.child_ids:
                task = Task(
                    task_id=f"{child_id}_task",
                    title=f"Sub-goal: {child_id[:8]}",
                    description=f"Execute sub-goal {child_id}",
                    task_type=TaskType.ACTION,
                    estimated_duration=30.0,
                    priority=parent_task.priority
                )
                tasks.append(task)
        
        # Check metadata for decomposition hints
        if goal.metadata:
            if "steps" in goal.metadata:
                for i, step in enumerate(goal.metadata["steps"]):
                    task = Task(
                        task_id=f"{parent_task.task_id}_step_{i}",
                        title=step.get("title", f"Step {i+1}"),
                        description=step.get("description", ""),
                        task_type=TaskType.ACTION,
                        estimated_duration=step.get("duration", 60.0),
                        priority=parent_task.priority
                    )
                    tasks.append(task)
        
        # Default decomposition
        if not tasks:
            tasks.append(Task(
                task_id=f"{parent_task.task_id}_default",
                title="Execute main task",
                description=goal.description,
                task_type=TaskType.ACTION,
                estimated_duration=60.0,
                priority=parent_task.priority
            ))
        
        return tasks
    
    # =========================================================================
    # DEPENDENCY DETECTION
    # =========================================================================
    
    def _detect_dependencies(self, graph: TaskGraph) -> None:
        """
        Detect dependencies between tasks in the graph.
        
        Args:
            graph: Task graph to analyze
        """
        tasks = list(graph.tasks.values())
        
        for i, task in enumerate(tasks):
            for j, other in enumerate(tasks):
                if i >= j:
                    continue
                
                # Check for implicit dependencies
                if self._has_dependency(task, other):
                    if other.task_id not in task.dependencies:
                        graph.add_edge(other.task_id, task.task_id)
    
    def _has_dependency(self, task: Task, dependency: Task) -> bool:
        """Check if task depends on another task."""
        # Check description for dependency hints
        desc_lower = task.description.lower()
        dep_title_lower = dependency.title.lower()
        
        # Keyword-based detection
        dependency_keywords = [
            f"before {dep_title_lower[:20]}",
            f"after {dep_title_lower[:20]}",
            f"following {dep_title_lower[:20]}"
        ]
        
        for keyword in dependency_keywords:
            if keyword in desc_lower:
                return True
        
        # Resource conflict detection
        task_resources = {r.type for r in task.required_resources}
        dep_resources = {r.type for r in dependency.required_resources}
        
        # Same resource type creates potential dependency
        if task_resources & dep_resources:
            # More complex: check if same resource instance
            for task_r in task.required_resources:
                for dep_r in dependency.required_resources:
                    if task_r.type == dep_r.type and task_r.resource_id == dep_r.resource_id:
                        return True
        
        return False
    
    def _detect_text_dependencies(self, tasks: List[Task]) -> None:
        """Detect dependencies from text descriptions."""
        for i, task in enumerate(tasks):
            desc_lower = task.description.lower()
            
            # Look for "before X" or "after X" patterns
            for j, other in enumerate(tasks):
                if i <= j:
                    continue
                
                other_title = other.title.lower()
                
                if f"before {other_title[:20]}" in desc_lower:
                    task.dependencies.append(other.task_id)
                elif f"after {other_title[:20]}" in desc_lower:
                    task.dependencies.append(other.task_id)
    
    # =========================================================================
    # PARALLELIZATION
    # =========================================================================
    
    def _mark_parallel_tasks(self, graph: TaskGraph) -> None:
        """Mark tasks that can be executed in parallel."""
        tasks = list(graph.tasks.values())
        
        for task in tasks:
            # Check if all dependencies are satisfied by completed tasks
            if not task.dependencies:
                task.execution_mode = TaskType.ACTION
                continue
            
            # If dependencies are parallel, this can be parallel too
            all_deps_parallel = all(
                graph.tasks[dep_id].execution_mode == TaskType.ACTION
                for dep_id in task.dependencies
                if dep_id in graph.tasks
            )
            
            if all_deps_parallel:
                task.execution_mode = TaskType.ACTION
    
    def find_parallel_groups(self, graph: TaskGraph) -> List[List[str]]:
        """
        Find groups of tasks that can be executed in parallel.
        
        Returns:
            List of task ID groups
        """
        groups = []
        processed = set()
        
        for task in graph.tasks.values():
            if task.task_id in processed:
                continue
            
            # Find all tasks that can run with this one
            group = [task.task_id]
            processed.add(task.task_id)
            
            for other in graph.tasks.values():
                if other.task_id in processed:
                    continue
                
                # Check if can run in parallel
                if self._can_run_parallel(graph, task, other):
                    group.append(other.task_id)
                    processed.add(other.task_id)
            
            groups.append(group)
        
        return groups
    
    def _can_run_parallel(self, graph: TaskGraph, task1: Task, task2: Task) -> bool:
        """Check if two tasks can run in parallel."""
        # Check dependencies
        if task2.task_id in task1.dependencies or task1.task_id in task2.dependencies:
            return False
        
        # Check for shared dependencies
        for dep_id in task1.dependencies:
            if dep_id in task2.dependencies:
                # Check if dependency is already complete
                if graph.tasks.get(dep_id, Task(task_id="", title="")).status != TaskStatus.COMPLETED:
                    return False
        
        # Check resource conflicts
        task1_resources = {(r.type, r.resource_id) for r in task1.required_resources}
        task2_resources = {(r.type, r.resource_id) for r in task2.required_resources}
        
        if task1_resources & task2_resources:
            return False
        
        return True
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _split_text_segments(self, text: str) -> List[str]:
        """Split text into logical segments."""
        # Split by common delimiters
        segments = re.split(r'[.;]\s*', text)
        
        # Also split by numbered lists
        numbered = re.split(r'\n\s*\d+[.)]\s*', text)
        if len(numbered) > 1:
            segments.extend(numbered)
        
        # Split by conjunctions that suggest parallelization
        parallel_markers = [' and then ', ' and ', ' also ', ' additionally ']
        for marker in parallel_markers:
            for segment in segments[:]:
                if marker in segment:
                    parts = segment.split(marker)
                    segments.remove(segment)
                    segments.extend(parts)
        
        return [s.strip() for s in segments if s.strip()]
    
    def _detect_execution_mode(self, text: str) -> Tuple[str, str]:
        """Detect execution mode from text."""
        text_lower = text.lower()
        
        if any(k in text_lower for k in [' and ', ' simultaneously ', '同时']):
            return "parallel", text
        elif any(k in text_lower for k in [' if ', ' when ', ' depending ']):
            return "conditional", text
        elif any(k in text_lower for k in [' each ', ' every ', ' repeat ']):
            return "loop", text
        
        return "sequential", text
    
    def _extract_title(self, text: str) -> str:
        """Extract title from text."""
        # Take first sentence or first N characters
        text = text.strip()
        if len(text) <= 50:
            return text
        
        # Find first sentence boundary
        for boundary in ['.', '!', '?']:
            if boundary in text:
                idx = text.index(boundary)
                return text[:idx].strip()
        
        return text[:50] + "..."
    
    def _detect_task_type(self, text: str) -> TaskType:
        """Detect task type from text."""
        text_lower = text.lower()
        
        if any(k in text_lower for k in ['research', 'find', 'search', 'lookup', 'بحث']):
            return TaskType.QUERY
        elif any(k in text_lower for k in ['analyze', 'examine', 'evaluate', 'تحليل']):
            return TaskType.ANALYSIS
        elif any(k in text_lower for k in ['verify', 'check', 'validate', 'تأكد']):
            return TaskType.VERIFICATION
        elif any(k in text_lower for k in ['decide', 'choose', 'select', 'قرار']):
            return TaskType.DECISION
        elif any(k in text_lower for k in ['combine', 'merge', 'create', 'build']):
            return TaskType.SYNTHESIS
        
        return TaskType.ACTION
    
    def _estimate_duration(self, text: str) -> float:
        """Estimate task duration from text."""
        # Look for time indicators
        time_patterns = [
            (r'(\d+)\s*hours?', 3600),
            (r'(\d+)\s*minutes?', 60),
            (r'(\d+)\s*seconds?', 1),
        ]
        
        text_lower = text.lower()
        for pattern, multiplier in time_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return float(int(match.group(1))) * multiplier
        
        # Default estimate based on task type
        task_type = self._detect_task_type(text)
        defaults = {
            TaskType.QUERY: 30.0,
            TaskType.ANALYSIS: 60.0,
            TaskType.VERIFICATION: 20.0,
            TaskType.DECISION: 15.0,
            TaskType.SYNTHESIS: 45.0,
            TaskType.ACTION: 30.0,
        }
        
        return defaults.get(task_type, 30.0)
    
    def _estimate_from_goal(self, goal: Goal) -> float:
        """Estimate duration based on goal."""
        base = 60.0
        
        # Adjust based on depth
        base *= (1 + goal.depth * 0.2)
        
        # Adjust based on children
        if goal.child_ids:
            base *= (1 + len(goal.child_ids) * 0.3)
        
        return base
    
    def _calculate_priority(self, text: str, context: Dict[str, Any]) -> int:
        """Calculate task priority."""
        text_lower = text.lower()
        priority = 5
        
        # Increase for urgent keywords
        if any(k in text_lower for k in ['urgent', 'asap', 'immediately', 'فوراً']):
            priority = 2
        elif any(k in text_lower for k in ['important', 'critical', ' важно']):
            priority = 3
        
        # Decrease for optional
        if any(k in text_lower for k in ['optional', 'if time', 'عند توفر']):
            priority = 7
        
        return priority
    
    def _priority_to_int(self, priority: GoalPriority) -> int:
        """Convert GoalPriority to integer."""
        mapping = {
            GoalPriority.CRITICAL: 1,
            GoalPriority.HIGH: 3,
            GoalPriority.MEDIUM: 5,
            GoalPriority.LOW: 7
        }
        return mapping.get(priority, 5)
    
    # =========================================================================
    # QUERIES
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get decomposer statistics."""
        return {
            "goals_decomposed": self._decomposed_count,
            "templates_available": len(self._task_templates),
            "rules_available": len(self._decomposition_rules)
        }


# ============================================================================
# SINGLETON ACCESSOR
# ============================================================================

_task_decomposer_instance: Optional[TaskDecomposer] = None


def get_task_decomposer() -> TaskDecomposer:
    """Get singleton instance of TaskDecomposer."""
    global _task_decomposer_instance
    if _task_decomposer_instance is None:
        _task_decomposer_instance = TaskDecomposer()
    return _task_decomposer_instance
