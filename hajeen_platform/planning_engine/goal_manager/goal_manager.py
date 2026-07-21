"""
Goal Manager - Planning Engine v1.0
===================================

Manages goals, hierarchies, priorities, and state tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.base import BaseComponent, PlanningContext
from ..core.models import (
    Goal, GoalPriority, GoalStatus, GoalTree,
    TaskStatus, Task
)


class GoalManager(BaseComponent):
    """
    Manages goals throughout the planning lifecycle.
    
    Responsibilities:
    - Create and manage goals
    - Build goal hierarchies
    - Track goal state
    - Calculate priorities
    - Decompose goals into sub-goals
    """
    
    def __init__(self):
        super().__init__()
        self._goals: Dict[str, Goal] = {}
        self._goal_trees: Dict[str, GoalTree] = {}
        self._active_goal_id: Optional[str] = None
    
    async def _async_initialize(self) -> None:
        """Initialize the goal manager."""
        self.logger.info("GoalManager initialized")
    
    # =========================================================================
    # GOAL CREATION
    # =========================================================================
    
    def create_goal(
        self,
        title: str,
        description: str = "",
        priority: GoalPriority = GoalPriority.MEDIUM,
        parent_id: Optional[str] = None,
        success_criteria: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Goal:
        """
        Create a new goal.
        
        Args:
            title: Goal title
            description: Detailed description
            priority: Goal priority
            parent_id: Parent goal ID for hierarchy
            success_criteria: List of success criteria
            metadata: Additional metadata
            
        Returns:
            Created Goal object
        """
        goal_id = str(uuid.uuid4())
        
        # Calculate depth
        depth = 0
        if parent_id and parent_id in self._goals:
            depth = self._goals[parent_id].depth + 1
        
        # Create goal
        goal = Goal(
            goal_id=goal_id,
            title=title,
            description=description,
            priority=priority,
            status=GoalStatus.PENDING,
            parent_id=parent_id,
            depth=depth,
            success_criteria=success_criteria or [],
            metadata=metadata or {}
        )
        
        # Build path
        if parent_id:
            parent = self._goals.get(parent_id)
            if parent:
                goal.path = parent.path + [parent_id]
        
        # Store goal
        self._goals[goal_id] = goal
        
        # Update parent
        if parent_id and parent_id in self._goals:
            self._goals[parent_id].add_child(goal_id)
        
        self.logger.info(f"Created goal: {goal_id} - {title}")
        self.record_metric("goals_created", len(self._goals))
        
        return goal
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        return self._goals.get(goal_id)
    
    def get_all_goals(self) -> List[Goal]:
        """Get all goals."""
        return list(self._goals.values())
    
    # =========================================================================
    # GOAL TREE MANAGEMENT
    # =========================================================================
    
    def create_goal_tree(self, root_goal_id: str) -> GoalTree:
        """
        Create a goal tree from a root goal.
        
        Args:
            root_goal_id: ID of the root goal
            
        Returns:
            GoalTree object
        """
        tree = GoalTree()
        tree.root_goals = [root_goal_id]
        tree.goals = {root_goal_id: self._goals[root_goal_id]}
        
        # Add all descendants
        queue = [root_goal_id]
        while queue:
            current_id = queue.pop(0)
            current = self._goals.get(current_id)
            if not current:
                continue
                
            for child_id in current.child_ids:
                if child_id in self._goals:
                    child = self._goals[child_id]
                    tree.goals[child_id] = child
                    if child.parent_id == root_goal_id:
                        tree.edges.append((root_goal_id, child_id))
                    else:
                        tree.edges.append((current_id, child_id))
                    queue.append(child_id)
        
        self._goal_trees[root_goal_id] = tree
        self.logger.info(f"Created goal tree for: {root_goal_id}")
        
        return tree
    
    def get_goal_tree(self, root_goal_id: str) -> Optional[GoalTree]:
        """Get an existing goal tree."""
        return self._goal_trees.get(root_goal_id)
    
    def get_subtree(self, goal_id: str) -> GoalTree:
        """Get subtree starting from a goal."""
        subtree = GoalTree()
        subtree.root_goals = [goal_id]
        
        queue = [goal_id]
        while queue:
            current_id = queue.pop(0)
            current = self._goals.get(current_id)
            if not current:
                continue
                
            subtree.goals[current_id] = current
            
            for child_id in current.child_ids:
                if child_id in self._goals:
                    subtree.edges.append((current_id, child_id))
                    queue.append(child_id)
        
        return subtree
    
    # =========================================================================
    # GOAL DECOMPOSITION
    # =========================================================================
    
    def decompose_goal(
        self,
        goal_id: str,
        sub_goals: List[Dict[str, Any]]
    ) -> List[Goal]:
        """
        Decompose a goal into sub-goals.
        
        Args:
            goal_id: Parent goal ID
            sub_goals: List of sub-goal definitions
            
        Returns:
            List of created sub-goals
        """
        parent = self._goals.get(goal_id)
        if not parent:
            raise ValueError(f"Goal not found: {goal_id}")
        
        created_goals = []
        for sg in sub_goals:
            sub_goal = self.create_goal(
                title=sg.get("title", "Sub-goal"),
                description=sg.get("description", ""),
                priority=sg.get("priority", GoalPriority.MEDIUM),
                parent_id=goal_id,
                success_criteria=sg.get("criteria", []),
                metadata=sg.get("metadata", {})
            )
            created_goals.append(sub_goal)
        
        self.logger.info(f"Decomposed goal {goal_id} into {len(created_goals)} sub-goals")
        return created_goals
    
    def decompose_to_tasks(
        self,
        goal: Goal,
        task_definitions: List[Dict[str, Any]]
    ) -> List[Task]:
        """
        Decompose a goal directly into tasks.
        
        Args:
            goal: Goal to decompose
            task_definitions: List of task definitions
            
        Returns:
            List of created tasks
        """
        from ..core.models import Task, TaskType
        
        tasks = []
        for i, td in enumerate(task_definitions):
            task = Task(
                task_id=f"{goal.goal_id}_task_{i}",
                title=td.get("title", f"Task {i}"),
                description=td.get("description", ""),
                task_type=TaskType(td.get("type", "action")),
                estimated_duration=td.get("duration", 60.0),
                priority=td.get("priority", 5),
                input_data=td.get("input", {})
            )
            tasks.append(task)
        
        self.logger.info(f"Decomposed goal {goal.goal_id} into {len(tasks)} tasks")
        return tasks
    
    # =========================================================================
    # GOAL STATE MANAGEMENT
    # =========================================================================
    
    def activate_goal(self, goal_id: str) -> bool:
        """
        Activate a goal for execution.
        
        Args:
            goal_id: Goal ID
            
        Returns:
            True if activated successfully
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        
        if goal.status != GoalStatus.PENDING:
            return False
        
        # Check if parent is active or completed
        if goal.parent_id:
            parent = self._goals.get(goal.parent_id)
            if parent and parent.status not in [GoalStatus.ACTIVE, GoalStatus.COMPLETED]:
                goal.status = GoalStatus.BLOCKED
                return False
        
        goal.status = GoalStatus.ACTIVE
        goal.updated_at = datetime.utcnow()
        self._active_goal_id = goal_id
        
        self.logger.info(f"Activated goal: {goal_id}")
        return True
    
    def complete_goal(self, goal_id: str, success: bool = True) -> bool:
        """
        Mark a goal as completed.
        
        Args:
            goal_id: Goal ID
            success: Whether goal was completed successfully
            
        Returns:
            True if completed successfully
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        
        goal.status = GoalStatus.COMPLETED if success else GoalStatus.FAILED
        goal.completed_at = datetime.utcnow()
        goal.progress = 1.0 if success else 0.0
        goal.updated_at = datetime.utcnow()
        
        # Update parent's progress
        self._update_parent_progress(goal_id)
        
        # Check if parent can now be activated
        if goal.parent_id:
            self._check_parent_activation(goal.parent_id)
        
        self.logger.info(f"Completed goal: {goal_id} (success={success})")
        return True
    
    def _update_parent_progress(self, child_id: str) -> None:
        """Update parent's progress based on child completion."""
        child = self._goals.get(child_id)
        if not child or not child.parent_id:
            return
        
        parent = self._goals.get(child.parent_id)
        if not parent:
            return
        
        # Calculate progress from all children
        completed = sum(
            1 for cid in parent.child_ids
            if cid in self._goals and self._goals[cid].status == GoalStatus.COMPLETED
        )
        total = len(parent.child_ids)
        
        if total > 0:
            parent.progress = completed / total
            parent.updated_at = datetime.utcnow()
    
    def _check_parent_activation(self, parent_id: str) -> None:
        """Check if parent can now be activated."""
        parent = self._goals.get(parent_id)
        if not parent or parent.status != GoalStatus.BLOCKED:
            return
        
        # Check if all blocking children are complete
        all_complete = all(
            cid in self._goals and self._goals[cid].status in [GoalStatus.COMPLETED, GoalStatus.SKIPPED]
            for cid in parent.child_ids
        )
        
        if all_complete:
            self.activate_goal(parent_id)
    
    # =========================================================================
    # PRIORITY CALCULATION
    # =========================================================================
    
    def calculate_priority(
        self,
        goal_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> GoalPriority:
        """
        Calculate or update goal priority.
        
        Args:
            goal_id: Goal ID
            context: Additional context for priority calculation
            
        Returns:
            Calculated priority
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return GoalPriority.MEDIUM
        
        # Priority factors
        deadline_factor = 0.0
        dependency_factor = 0.0
        value_factor = 0.0
        
        # Deadline urgency
        if context and "deadline" in context:
            deadline = context["deadline"]
            if deadline:
                time_left = (deadline - datetime.utcnow()).total_seconds()
                if time_left < 3600:  # Less than 1 hour
                    deadline_factor = 0.3
                elif time_left < 86400:  # Less than 1 day
                    deadline_factor = 0.2
        
        # Dependency count
        if goal.child_ids:
            dependency_factor = min(0.3, len(goal.child_ids) * 0.05)
        
        # Strategic value
        if context and "strategic_value" in context:
            value_factor = min(0.2, context["strategic_value"] * 0.2)
        
        # Calculate priority score
        priority_score = deadline_factor + dependency_factor + value_factor
        
        # Map to priority
        if priority_score >= 0.6:
            new_priority = GoalPriority.CRITICAL
        elif priority_score >= 0.4:
            new_priority = GoalPriority.HIGH
        elif priority_score >= 0.2:
            new_priority = GoalPriority.MEDIUM
        else:
            new_priority = GoalPriority.LOW
        
        goal.priority = new_priority
        return new_priority
    
    def get_execution_order(self) -> List[str]:
        """
        Get goals in execution order (topological sort).
        
        Returns:
            List of goal IDs in execution order
        """
        in_degree = {gid: 0 for gid in self._goals}
        
        for goal in self._goals.values():
            if goal.parent_id and goal.parent_id in self._goals:
                in_degree[goal.goal_id] += 1
        
        # Topological sort
        queue = [gid for gid, deg in in_degree.items() if deg == 0]
        result = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            goal = self._goals[current]
            for child_id in goal.child_ids:
                if child_id in in_degree:
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        queue.append(child_id)
        
        return result
    
    # =========================================================================
    # QUERIES
    # =========================================================================
    
    def get_active_goals(self) -> List[Goal]:
        """Get all active goals."""
        return [g for g in self._goals.values() if g.status == GoalStatus.ACTIVE]
    
    def get_pending_goals(self) -> List[Goal]:
        """Get all pending goals."""
        return [g for g in self._goals.values() if g.status == GoalStatus.PENDING]
    
    def get_blocked_goals(self) -> List[Goal]:
        """Get all blocked goals."""
        return [g for g in self._goals.values() if g.status == GoalStatus.BLOCKED]
    
    def get_goals_by_priority(self, priority: GoalPriority) -> List[Goal]:
        """Get all goals with a specific priority."""
        return [g for g in self._goals.values() if g.priority == priority]
    
    def get_root_goals(self) -> List[Goal]:
        """Get all root-level goals (no parent)."""
        return [g for g in self._goals.values() if g.parent_id is None]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get goal statistics."""
        return {
            "total_goals": len(self._goals),
            "active": len(self.get_active_goals()),
            "pending": len(self.get_pending_goals()),
            "completed": len([g for g in self._goals.values() if g.status == GoalStatus.COMPLETED]),
            "failed": len([g for g in self._goals.values() if g.status == GoalStatus.FAILED]),
            "blocked": len(self.get_blocked_goals()),
            "by_priority": {
                "critical": len(self.get_goals_by_priority(GoalPriority.CRITICAL)),
                "high": len(self.get_goals_by_priority(GoalPriority.HIGH)),
                "medium": len(self.get_goals_by_priority(GoalPriority.MEDIUM)),
                "low": len(self.get_goals_by_priority(GoalPriority.LOW)),
            }
        }


# ============================================================================
# SINGLETON ACCESSOR
# ============================================================================

_goal_manager_instance: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    """Get singleton instance of GoalManager."""
    global _goal_manager_instance
    if _goal_manager_instance is None:
        _goal_manager_instance = GoalManager()
    return _goal_manager_instance
