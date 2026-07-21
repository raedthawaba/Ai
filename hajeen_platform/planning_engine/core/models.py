"""
Core Models for Planning Engine v1.0
====================================

This module contains all Pydantic models for the Planning Engine.
All models are fully typed and validated.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# ENUMS
# ============================================================================

class GoalStatus(str, Enum):
    """Status of a goal."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class GoalPriority(str, Enum):
    """Priority levels for goals."""
    CRITICAL = "critical"  # P0
    HIGH = "high"          # P1
    MEDIUM = "medium"      # P2
    LOW = "low"           # P3


class TaskStatus(str, Enum):
    """Status of a task."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskType(str, Enum):
    """Types of tasks."""
    ACTION = "action"
    QUERY = "query"
    VERIFICATION = "verification"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    DECISION = "decision"


class ExecutionMode(str, Enum):
    """Execution modes for tasks."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    LOOP = "loop"


class ResourceType(str, Enum):
    """Types of resources."""
    TIME = "time"
    MEMORY = "memory"
    COMPUTE = "compute"
    NETWORK = "network"
    STORAGE = "storage"
    CREDITS = "credits"
    PERMISSION = "permission"


class RiskLevel(str, Enum):
    """Risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlanStatus(str, Enum):
    """Status of a plan."""
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ExecutionStrategyType(str, Enum):
    """Types of execution strategies."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    EVENT_DRIVEN = "event_driven"
    HYBRID = "hybrid"


# ============================================================================
# RESOURCE MODELS
# ============================================================================

class Resource(BaseModel):
    """Represents a resource required for task execution."""
    resource_id: str = Field(..., description="Unique identifier")
    type: ResourceType = Field(..., description="Type of resource")
    name: str = Field(..., description="Resource name")
    quantity: float = Field(default=1.0, description="Amount required")
    unit: str = Field(default="units", description="Unit of measurement")
    available: float = Field(default=1.0, description="Available quantity")
    reserved: float = Field(default=0.0, description="Reserved quantity")
    
    @property
    def remaining(self) -> float:
        """Get remaining available quantity."""
        return self.available - self.reserved
    
    @property
    def is_available(self) -> bool:
        """Check if resource is available."""
        return self.remaining >= self.quantity


class ResourceAllocation(BaseModel):
    """Allocation of resources to a task."""
    task_id: str = Field(..., description="Task ID")
    resource_id: str = Field(..., description="Resource ID")
    allocated_quantity: float = Field(..., description="Allocated quantity")
    start_time: Optional[datetime] = Field(None, description="Allocation start")
    end_time: Optional[datetime] = Field(None, description="Allocation end")


# ============================================================================
# GOAL MODELS
# ============================================================================

class Goal(BaseModel):
    """Represents a goal in the planning system."""
    goal_id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Goal title")
    description: str = Field(default="", description="Goal description")
    priority: GoalPriority = Field(default=GoalPriority.MEDIUM)
    status: GoalStatus = Field(default=GoalStatus.PENDING)
    parent_id: Optional[str] = Field(None, description="Parent goal ID")
    child_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Metrics
    success_criteria: List[str] = Field(default_factory=list)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Hierarchy
    depth: int = Field(default=0, description="Depth in goal tree")
    path: List[str] = Field(default_factory=list, description="Path from root")
    
    def add_child(self, child_id: str) -> None:
        """Add a child goal."""
        if child_id not in self.child_ids:
            self.child_ids.append(child_id)
    
    def complete(self) -> None:
        """Mark goal as completed."""
        self.status = GoalStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.progress = 1.0


class GoalTree(BaseModel):
    """Hierarchical structure of goals."""
    root_goals: List[str] = Field(default_factory=list)
    goals: Dict[str, Goal] = Field(default_factory=dict)
    edges: List[tuple[str, str]] = Field(default_factory=list)
    
    def add_goal(self, goal: Goal) -> None:
        """Add a goal to the tree."""
        self.goals[goal.goal_id] = goal
        if goal.parent_id is None and goal.goal_id not in self.root_goals:
            self.root_goals.append(goal.goal_id)
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        return self.goals.get(goal_id)
    
    def get_children(self, goal_id: str) -> List[Goal]:
        """Get all child goals."""
        goal = self.goals.get(goal_id)
        if not goal:
            return []
        return [self.goals[cid] for cid in goal.child_ids if cid in self.goals]
    
    def get_depth(self) -> int:
        """Get maximum depth of the tree."""
        if not self.goals:
            return 0
        return max(g.depth for g in self.goals.values())


# ============================================================================
# TASK MODELS
# ============================================================================

class TaskDependency(BaseModel):
    """Represents a dependency between tasks."""
    source_id: str = Field(..., description="Source task ID")
    target_id: str = Field(..., description="Target task ID")
    dependency_type: str = Field(default="finish_to_start", description="Type of dependency")
    delay: float = Field(default=0.0, description="Delay in seconds")


class Task(BaseModel):
    """Represents a task in the execution plan."""
    task_id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task description")
    task_type: TaskType = Field(default=TaskType.ACTION)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    
    # Execution
    execution_mode: ExecutionMode = Field(default=ExecutionMode.SEQUENTIAL)
    estimated_duration: float = Field(default=0.0, description="Estimated duration in seconds")
    actual_duration: Optional[float] = Field(None)
    
    # Dependencies
    dependencies: List[str] = Field(default_factory=list)
    dependents: List[str] = Field(default_factory=list)
    
    # Resources
    required_resources: List[Resource] = Field(default_factory=list)
    allocated_resources: List[ResourceAllocation] = Field(default_factory=list)
    
    # Priority
    priority: int = Field(default=5, ge=1, le=10)
    
    # State
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = Field(None)
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    
    # Metrics
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    
    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.utcnow()
    
    def complete(self, output: Optional[Dict[str, Any]] = None) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if output:
            self.output_data = output
        if self.started_at:
            self.actual_duration = (self.completed_at - self.started_at).total_seconds()
        self.progress = 1.0
    
    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.utcnow()


class TaskGraph(BaseModel):
    """Directed Acyclic Graph of tasks."""
    tasks: Dict[str, Task] = Field(default_factory=dict)
    edges: List[TaskDependency] = Field(default_factory=list)
    
    def add_task(self, task: Task) -> None:
        """Add a task to the graph."""
        self.tasks[task.task_id] = task
    
    def add_edge(self, source_id: str, target_id: str, 
                 dependency_type: str = "finish_to_start") -> None:
        """Add an edge between tasks."""
        # Update task dependencies
        if target_id in self.tasks and source_id not in self.tasks[target_id].dependencies:
            self.tasks[target_id].dependencies.append(source_id)
        if source_id in self.tasks and target_id not in self.tasks[source_id].dependents:
            self.tasks[source_id].dependents.append(target_id)
        
        # Add edge
        edge = TaskDependency(
            source_id=source_id,
            target_id=target_id,
            dependency_type=dependency_type
        )
        self.edges.append(edge)
    
    def get_ready_tasks(self) -> List[Task]:
        """Get tasks that are ready to execute (all dependencies met)."""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            all_deps_complete = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            if all_deps_complete:
                task.status = TaskStatus.READY
                ready.append(task)
        return ready
    
    def get_topological_order(self) -> List[str]:
        """Get tasks in topological order for execution."""
        # Calculate in-degrees
        in_degree = {tid: 0 for tid in self.tasks}
        for task in self.tasks.values():
            for dep in task.dependencies:
                if dep in self.tasks:
                    in_degree[task.task_id] += 1
        
        # Kahn's algorithm
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        result = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            for dependent in self.tasks[current].dependents:
                if dependent in self.tasks:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        return result
    
    def has_cycle(self) -> bool:
        """Check if the graph has a cycle."""
        visited = set()
        rec_stack = set()
        
        def dfs(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            for dep in self.tasks.get(task_id, Task(task_id="", title="")).dependencies:
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True
            
            rec_stack.remove(task_id)
            return False
        
        for task_id in self.tasks:
            if task_id not in visited:
                if dfs(task_id):
                    return True
        
        return False


# ============================================================================
# EXECUTION GRAPH
# ============================================================================

class ExecutionNode(BaseModel):
    """Node in the execution graph."""
    node_id: str = Field(..., description="Unique identifier")
    task_id: str = Field(..., description="Associated task ID")
    execution_order: int = Field(..., description="Order in execution")
    estimated_start: Optional[datetime] = Field(None)
    estimated_end: Optional[datetime] = Field(None)
    actual_start: Optional[datetime] = Field(None)
    actual_end: Optional[datetime] = Field(None)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    worker_id: Optional[str] = Field(None, description="Assigned worker")


class ExecutionGraph(BaseModel):
    """Complete execution plan with scheduling."""
    graph_id: str = Field(..., description="Unique identifier")
    plan_id: str = Field(..., description="Associated plan ID")
    nodes: Dict[str, ExecutionNode] = Field(default_factory=dict)
    edges: List[tuple[str, str]] = Field(default_factory=list)
    
    # Scheduling
    start_time: Optional[datetime] = Field(None)
    end_time: Optional[datetime] = Field(None)
    total_duration: float = Field(default=0.0)
    
    def add_node(self, node: ExecutionNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.node_id] = node
    
    def get_critical_path(self) -> List[str]:
        """Get the critical path (longest path through the graph)."""
        # Simplified: return topological order with longest duration
        ordered = []
        max_duration = {}
        
        for node_id in self.nodes:
            duration = self.nodes[node_id].estimated_end.timestamp() - \
                      self.nodes[node_id].estimated_start.timestamp() if \
                      self.nodes[node_id].estimated_end and \
                      self.nodes[node_id].estimated_start else 0
            max_duration[node_id] = duration
        
        return sorted(max_duration.keys(), key=lambda x: max_duration[x], reverse=True)


# ============================================================================
# RISK MODELS
# ============================================================================

class Risk(BaseModel):
    """Represents a risk in the plan."""
    risk_id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Risk title")
    description: str = Field(..., description="Risk description")
    level: RiskLevel = Field(..., description="Risk level")
    probability: float = Field(..., ge=0.0, le=1.0, description="Probability of occurrence")
    impact: float = Field(..., ge=0.0, le=1.0, description="Impact if occurs")
    
    # Affected elements
    affected_tasks: List[str] = Field(default_factory=list)
    affected_resources: List[str] = Field(default_factory=list)
    
    # Mitigation
    mitigation_strategy: str = Field(default="", description="How to mitigate")
    contingency_plan: str = Field(default="", description="Plan B if risk occurs")
    fallback_task_id: Optional[str] = Field(None, description="Alternative task")
    
    # Status
    status: str = Field(default="identified")
    is_mitigated: bool = Field(default=False)


class RiskAnalysis(BaseModel):
    """Complete risk analysis for a plan."""
    risks: List[Risk] = Field(default_factory=list)
    total_risk_score: float = Field(default=0.0)
    critical_risks: List[str] = Field(default_factory=list)
    risk_mitigation_cost: float = Field(default=0.0)
    
    def add_risk(self, risk: Risk) -> None:
        """Add a risk to the analysis."""
        self.risks.append(risk)
        self.total_risk_score += risk.probability * risk.impact
        if risk.level == RiskLevel.CRITICAL:
            self.critical_risks.append(risk.risk_id)


# ============================================================================
# PLAN MODELS
# ============================================================================

class AlternativePlan(BaseModel):
    """An alternative plan option."""
    plan_id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Plan title")
    description: str = Field(..., description="Plan description")
    
    # Metrics
    estimated_duration: float = Field(default=0.0)
    estimated_cost: float = Field(default=0.0)
    success_probability: float = Field(default=0.0)
    risk_score: float = Field(default=0.0)
    
    # Components
    goal_tree: Optional[GoalTree] = Field(None)
    task_graph: Optional[TaskGraph] = Field(None)
    execution_graph: Optional[ExecutionGraph] = Field(None)
    risk_analysis: Optional[RiskAnalysis] = Field(None)
    
    # Ranking
    rank: int = Field(default=0)
    selected: bool = Field(default=False)


class PlanValidation(BaseModel):
    """Result of plan validation."""
    is_valid: bool = Field(..., description="Is the plan valid")
    conflicts: List[str] = Field(default_factory=list)
    missing_tasks: List[str] = Field(default_factory=list)
    resource_conflicts: List[str] = Field(default_factory=list)
    circular_dependencies: List[str] = Field(default_factory=list)
    validation_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class Plan(BaseModel):
    """Complete execution plan."""
    plan_id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Plan title")
    description: str = Field(..., description="Plan description")
    
    # Status
    status: PlanStatus = Field(default=PlanStatus.DRAFT)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Components
    goal_tree: GoalTree = Field(default_factory=GoalTree)
    task_graph: TaskGraph = Field(default_factory=TaskGraph)
    execution_graph: Optional[ExecutionGraph] = Field(None)
    risk_analysis: RiskAnalysis = Field(default_factory=RiskAnalysis)
    
    # Alternatives
    alternatives: List[AlternativePlan] = Field(default_factory=list)
    selected_plan_id: Optional[str] = Field(None)
    
    # Validation
    validation: Optional[PlanValidation] = Field(None)
    
    # Metrics
    estimated_duration: float = Field(default=0.0)
    estimated_cost: float = Field(default=0.0)
    confidence: float = Field(default=0.0)
    
    # Execution
    execution_strategy: ExecutionStrategyType = Field(default=ExecutionStrategyType.SEQUENTIAL)
    start_time: Optional[datetime] = Field(None)
    end_time: Optional[datetime] = Field(None)
    progress: float = Field(default=0.0)
    
    def validate(self) -> PlanValidation:
        """Validate the plan."""
        conflicts = []
        warnings = []
        
        # Check for cycles
        if self.task_graph.has_cycle():
            conflicts.append("Task graph contains circular dependencies")
        
        # Check for missing dependencies
        for task in self.task_graph.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in self.task_graph.tasks:
                    conflicts.append(f"Task {task.task_id} depends on missing task {dep_id}")
        
        # Check resource conflicts
        # (simplified - full implementation would check for over-allocation)
        
        is_valid = len(conflicts) == 0
        
        self.validation = PlanValidation(
            is_valid=is_valid,
            conflicts=conflicts,
            warnings=warnings
        )
        
        return self.validation
    
    def select_best_alternative(self) -> Optional[AlternativePlan]:
        """Select the best alternative plan."""
        if not self.alternatives:
            return None
        
        # Score based on multiple factors
        for alt in self.alternatives:
            score = (
                alt.success_probability * 0.4 +
                (1 - alt.risk_score) * 0.3 +
                (1 - alt.estimated_cost / 1000) * 0.2 +
                (1 - alt.estimated_duration / 3600) * 0.1
            )
            alt.rank = int(score * 100)
        
        self.alternatives.sort(key=lambda x: x.rank, reverse=True)
        
        for alt in self.alternatives:
            if alt.is_valid if hasattr(alt, 'is_valid') else True:
                alt.selected = True
                self.selected_plan_id = alt.plan_id
                return alt
        
        return None


# ============================================================================
# PROGRESS MODELS
# ============================================================================

class ProgressSnapshot(BaseModel):
    """Snapshot of plan progress at a point in time."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    plan_id: str = Field(..., description="Plan ID")
    
    # Task progress
    total_tasks: int = Field(default=0)
    completed_tasks: int = Field(default=0)
    failed_tasks: int = Field(default=0)
    running_tasks: int = Field(default=0)
    pending_tasks: int = Field(default=0)
    
    # Time progress
    elapsed_time: float = Field(default=0.0)
    estimated_remaining: float = Field(default=0.0)
    eta: Optional[datetime] = Field(None)
    
    # Progress percentage
    progress_percentage: float = Field(default=0.0)
    
    # Milestones
    completed_milestones: List[str] = Field(default_factory=list)
    next_milestone: Optional[str] = Field(None)


class CompletionAnalysis(BaseModel):
    """Analysis of plan completion."""
    plan_id: str = Field(..., description="Plan ID")
    success: bool = Field(..., description="Was the plan successful")
    
    # Metrics
    total_duration: float = Field(default=0.0)
    estimated_duration: float = Field(default=0.0)
    accuracy: float = Field(default=0.0, description="Estimate accuracy")
    
    # Task analysis
    tasks_completed: int = Field(default=0)
    tasks_failed: int = Field(default=0)
    tasks_skipped: int = Field(default=0)
    
    # Goal analysis
    goals_achieved: int = Field(default=0)
    goals_partial: int = Field(default=0)
    goals_failed: int = Field(default=0)
    
    # Lessons learned
    success_factors: List[str] = Field(default_factory=list)
    failure_factors: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    
    # Recommendations
    recommendations: List[str] = Field(default_factory=list)


# ============================================================================
# PLANNING RESULT
# ============================================================================

class PlanningResult(BaseModel):
    """Complete result of the planning process."""
    result_id: str = Field(..., description="Unique identifier")
    reasoning_result: Dict[str, Any] = Field(..., description="Input from Reasoning Engine")
    
    # Generated plan
    plan: Plan = Field(..., description="Primary execution plan")
    
    # Goal structure
    goal_tree: GoalTree = Field(..., description="Goal hierarchy")
    
    # Task structure
    task_graph: TaskGraph = Field(..., description="Task dependencies")
    
    # Execution structure
    execution_graph: Optional[ExecutionGraph] = Field(None, description="Execution schedule")
    
    # Analysis
    risk_analysis: RiskAnalysis = Field(..., description="Risk assessment")
    alternatives: List[AlternativePlan] = Field(default_factory=list, description="Alternative plans")
    
    # Validation
    validation: PlanValidation = Field(..., description="Plan validation result")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    planning_duration: float = Field(default=0.0, description="Time taken to plan")
    
    # Metrics
    total_tasks: int = Field(default=0)
    total_goals: int = Field(default=0)
    estimated_duration: float = Field(default=0.0)
    estimated_cost: float = Field(default=0.0)
    confidence: float = Field(default=0.0)
    
    # Strategy
    execution_strategy: ExecutionStrategyType = Field(default=ExecutionStrategyType.SEQUENTIAL)
    
    # Rollback
    rollback_plan: Optional[Dict[str, Any]] = Field(None, description="Rollback instructions")
    
    @property
    def is_valid(self) -> bool:
        """Check if the plan is valid."""
        return self.validation.is_valid if self.validation else False
    
    def to_summary(self) -> Dict[str, Any]:
        """Generate a summary of the planning result."""
        return {
            "result_id": self.result_id,
            "is_valid": self.is_valid,
            "total_goals": self.total_goals,
            "total_tasks": self.total_tasks,
            "estimated_duration": self.estimated_duration,
            "estimated_cost": self.estimated_cost,
            "confidence": self.confidence,
            "execution_strategy": self.execution_strategy.value,
            "alternatives_count": len(self.alternatives),
            "risk_count": len(self.risk_analysis.risks),
        }
