"""
Constraint Solver - Planning Engine v1.0
=======================================

Solves constraints for planning optimization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from ..core.base import BaseComponent
from ..core.models import Task, TaskGraph, Resource, ResourceType


class ConstraintType(Enum):
    """Types of constraints."""
    TIME = "time"
    RESOURCE = "resource"
    BUDGET = "budget"
    PERMISSION = "permission"
    LOGICAL = "logical"
    ORDERING = "ordering"


@dataclass
class Constraint:
    """A planning constraint."""
    constraint_id: str
    type: ConstraintType
    description: str
    validator: Callable[[Any], bool]
    weight: float = 1.0
    is_hard: bool = True  # Hard constraints must be satisfied


class ConstraintSolver(BaseComponent):
    """
    Solves planning constraints.
    
    Responsibilities:
    - Define and manage constraints
    - Validate plans against constraints
    - Optimize for constraint satisfaction
    - Handle conflicting constraints
    """
    
    def __init__(self):
        super().__init__()
        self._constraints: Dict[str, Constraint] = {}
        self._constraint_violations: List[Dict[str, Any]] = []
    
    async def _async_initialize(self) -> None:
        """Initialize the constraint solver."""
        self._initialize_default_constraints()
        self.logger.info("ConstraintSolver initialized")
    
    def _initialize_default_constraints(self) -> None:
        """Initialize default constraints."""
        # Time constraint: no negative durations
        self.add_constraint(Constraint(
            constraint_id="no_negative_duration",
            type=ConstraintType.TIME,
            description="Task duration must be non-negative",
            validator=lambda t: t.get("duration", 0) >= 0,
            is_hard=True
        ))
        
        # Resource constraint: no over-allocation
        self.add_constraint(Constraint(
            constraint_id="no_over_allocation",
            type=ConstraintType.RESOURCE,
            description="Resources cannot be allocated beyond availability",
            validator=self._validate_resource_allocation,
            is_hard=True
        ))
        
        # Ordering constraint: no cycles
        self.add_constraint(Constraint(
            constraint_id="no_cycles",
            type=ConstraintType.ORDERING,
            description="Task graph must be acyclic",
            validator=lambda g: not g.has_cycle() if hasattr(g, 'has_cycle') else True,
            is_hard=True
        ))
    
    def add_constraint(self, constraint: Constraint) -> None:
        """Add a constraint."""
        self._constraints[constraint.constraint_id] = constraint
        self.logger.debug(f"Added constraint: {constraint.constraint_id}")
    
    def remove_constraint(self, constraint_id: str) -> None:
        """Remove a constraint."""
        if constraint_id in self._constraints:
            del self._constraints[constraint_id]
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def validate_task_graph(
        self,
        task_graph: TaskGraph,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate task graph against all constraints.
        
        Returns:
            Validation result with violations
        """
        violations = []
        warnings = []
        
        for constraint in self._constraints.values():
            result = self._check_constraint(constraint, task_graph, context)
            
            if not result["satisfied"]:
                violation = {
                    "constraint_id": constraint.constraint_id,
                    "type": constraint.type.value,
                    "description": constraint.description,
                    "is_hard": constraint.is_hard,
                    "details": result.get("details", "")
                }
                violations.append(violution)
                
                if not constraint.is_hard:
                    warnings.append(violation)
        
        hard_violations = [v for v in violations if v["is_hard"]]
        
        return {
            "is_valid": len(hard_violations) == 0,
            "violations": violations,
            "hard_violations": hard_violations,
            "warnings": warnings,
            "constraint_count": len(self._constraints)
        }
    
    def _check_constraint(
        self,
        constraint: Constraint,
        task_graph: TaskGraph,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check a single constraint."""
        try:
            # Prepare context for validator
            validator_context = {
                "task_graph": task_graph,
                "context": context or {}
            }
            
            result = constraint.validator(validator_context)
            
            if isinstance(result, bool):
                return {"satisfied": result, "details": ""}
            elif isinstance(result, dict):
                return result
            
            return {"satisfied": True, "details": ""}
            
        except Exception as e:
            return {
                "satisfied": False,
                "details": f"Constraint check error: {str(e)}"
            }
    
    # =========================================================================
    # OPTIMIZATION
    # =========================================================================
    
    def optimize_for_constraints(
        self,
        task_graph: TaskGraph,
        constraints: Optional[List[str]] = None
    ) -> TaskGraph:
        """
        Optimize task graph to satisfy constraints.
        
        Args:
            task_graph: Input task graph
            constraints: Specific constraints to optimize for
            
        Returns:
            Optimized task graph
        """
        # This is a simplified version - full implementation would use
        # constraint programming or linear programming
        
        violations = self.validate_task_graph(task_graph)
        
        if violations["is_valid"]:
            return task_graph
        
        # Try to fix soft constraint violations
        for violation in violations["warnings"]:
            task_graph = self._fix_violation(task_graph, violation)
        
        return task_graph
    
    def _fix_violation(self, task_graph: TaskGraph, violation: Dict) -> TaskGraph:
        """Attempt to fix a constraint violation."""
        # Simplified fixes based on violation type
        if violation["type"] == ConstraintType.RESOURCE.value:
            # Try to extend durations to avoid resource conflicts
            pass
        
        return task_graph
    
    # =========================================================================
    # CONSTRAINT TYPES
    # =========================================================================
    
    def create_time_constraint(
        self,
        task_id: str,
        start_after: Optional[datetime] = None,
        finish_before: Optional[datetime] = None,
        max_duration: Optional[float] = None
    ) -> Constraint:
        """Create a time-based constraint."""
        return Constraint(
            constraint_id=f"time_{task_id}",
            type=ConstraintType.TIME,
            description=f"Time constraints for task {task_id}",
            validator=lambda ctx: self._validate_time_constraint(ctx, task_id, start_after, finish_before, max_duration),
            is_hard=True
        )
    
    def _validate_time_constraint(
        self,
        context: Dict[str, Any],
        task_id: str,
        start_after: Optional[datetime],
        finish_before: Optional[datetime],
        max_duration: Optional[float]
    ) -> bool:
        """Validate time constraint."""
        task_graph = context["task_graph"]
        task = task_graph.tasks.get(task_id)
        
        if not task:
            return True  # Task doesn't exist, constraint satisfied
        
        if max_duration is not None and task.estimated_duration > max_duration:
            return False
        
        return True
    
    def create_resource_constraint(
        self,
        resource_id: str,
        max_allocation: float,
        allocation_type: str = "percentage"
    ) -> Constraint:
        """Create a resource-based constraint."""
        return Constraint(
            constraint_id=f"resource_{resource_id}",
            type=ConstraintType.RESOURCE,
            description=f"Resource allocation constraint for {resource_id}",
            validator=lambda ctx: self._validate_resource_constraint(ctx, resource_id, max_allocation, allocation_type),
            is_hard=True
        )
    
    def _validate_resource_constraint(
        self,
        context: Dict[str, Any],
        resource_id: str,
        max_allocation: float,
        allocation_type: str
    ) -> bool:
        """Validate resource constraint."""
        # Simplified - would calculate actual allocation
        return True
    
    def create_budget_constraint(
        self,
        max_cost: float
    ) -> Constraint:
        """Create a budget constraint."""
        return Constraint(
            constraint_id="budget_constraint",
            type=ConstraintType.BUDGET,
            description=f"Maximum budget: {max_cost}",
            validator=lambda ctx: self._validate_budget(ctx, max_cost),
            is_hard=True
        )
    
    def _validate_budget(
        self,
        context: Dict[str, Any],
        max_cost: float
    ) -> bool:
        """Validate budget constraint."""
        task_graph = context["task_graph"]
        
        # Calculate estimated cost
        total_cost = sum(
            task.estimated_duration * 0.01  # Simplified cost model
            for task in task_graph.tasks.values()
        )
        
        return total_cost <= max_cost
    
    def create_logical_constraint(
        self,
        description: str,
        condition: Callable[[Dict[str, Any]], bool]
    ) -> Constraint:
        """Create a logical constraint."""
        return Constraint(
            constraint_id=f"logical_{len(self._constraints)}",
            type=ConstraintType.LOGICAL,
            description=description,
            validator=lambda ctx: condition(ctx),
            is_hard=True
        )
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _validate_resource_allocation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate no resource over-allocation."""
        # Simplified implementation
        return {"satisfied": True, "details": ""}
    
    def get_violations_summary(self) -> Dict[str, Any]:
        """Get summary of all violations."""
        return {
            "total_violations": len(self._constraint_violations),
            "by_type": self._group_violations_by_type(),
            "hard_count": len([v for v in self._constraint_violations if v.get("is_hard")]),
            "soft_count": len([v for v in self._constraint_violations if not v.get("is_hard")])
        }
    
    def _group_violations_by_type(self) -> Dict[str, int]:
        """Group violations by type."""
        counts = {}
        for violation in self._constraint_violations:
            vtype = violation.get("type", "unknown")
            counts[vtype] = counts.get(vtype, 0) + 1
        return counts
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get constraint solver statistics."""
        return {
            "total_constraints": len(self._constraints),
            "constraints_by_type": {
                ct.value: len([
                    c for c in self._constraints.values()
                    if c.type == ct
                ])
                for ct in ConstraintType
            },
            "total_violations": len(self._constraint_violations)
        }


# ============================================================================
# SINGLETON
# ============================================================================

_constraint_solver_instance: Optional[ConstraintSolver] = None


def get_constraint_solver() -> ConstraintSolver:
    """Get singleton instance."""
    global _constraint_solver_instance
    if _constraint_solver_instance is None:
        _constraint_solver_instance = ConstraintSolver()
    return _constraint_solver_instance
