"""
Planning Contract - Interface for Planning Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base import BaseContract


class TaskStatus(str, Enum):
    """Status of a task"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task(BaseContract):
    """
    A single task in an execution plan.
    """
    task_id: str
    name: str
    description: str
    
    # Task properties
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    
    # Dependencies
    dependencies: List[str] = field(default_factory=list)
    
    # Resources
    estimated_tokens: int = 0
    estimated_duration_ms: float = 0.0
    
    # Execution
    assigned_model: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # Results
    result: Any = None
    error: Optional[str] = None


@dataclass
class ExecutionPlan(BaseContract):
    """
    A complete execution plan.
    """
    plan_id: str
    
    # Tasks
    tasks: List[Task] = field(default_factory=list)
    
    # Graph info
    can_parallelize: bool = False
    parallel_groups: List[List[str]] = field(default_factory=list)
    
    # Metadata
    total_estimated_tokens: int = 0
    total_estimated_duration_ms: float = 0.0


@dataclass
class PlanningResult(BaseContract):
    """
    Output from Planning Engine.
    
    This contract is passed from PlanningEngine to DecisionEngine.
    """
    success: bool
    
    # Goal info
    goal_id: str
    goal_description: str
    domain: str = "general"
    complexity: str = "medium"
    
    # Execution plan
    plan: Optional[ExecutionPlan] = None
    
    # Metrics
    planning_latency_ms: float = 0.0
    tasks_count: int = 0
    parallelizable: bool = False
    
    # Errors
    errors: List[str] = field(default_factory=list)
