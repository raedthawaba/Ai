# Planning Engine v1.0 Architecture

**Version**: 1.0.0  
**Status**: Production Ready  
**Date**: 2026-07-21

---

## Overview

The Planning Engine is a modular system that transforms Reasoning Engine output into executable plans. It operates independently from the Reasoning Engine and treats it as a decision source only.

```
Problem
   ↓
Reasoning (Reasoning Engine)
   ↓
Planning (Planning Engine) ← This Component
   ↓
Execution
   ↓
Monitoring
   ↓
Completion
```

---

## Architecture Layers

### 1. Goal Manager
**File**: `planning_engine/goal_manager/goal_manager.py`

**Responsibilities**:
- Create and manage goals
- Build goal hierarchies
- Track goal state
- Calculate priorities
- Decompose goals into sub-goals

**Key Methods**:
- `create_goal()` - Create new goal
- `decompose_goal()` - Split into sub-goals
- `activate_goal()` - Start goal execution
- `complete_goal()` - Mark as completed
- `calculate_priority()` - Dynamic priority

### 2. Task Decomposer
**File**: `planning_engine/task_decomposer/task_decomposer.py`

**Responsibilities**:
- Convert goals to tasks
- Detect dependencies
- Identify parallelizable tasks
- Recursive decomposition
- Task prioritization

**Key Methods**:
- `decompose_goal()` - Goal to task graph
- `decompose_text()` - Text to tasks
- `decompose_recursively()` - Multi-level
- `find_parallel_groups()` - Parallelization
- `_detect_dependencies()` - Dependency analysis

### 3. Graph Planner
**File**: `planning_engine/graph_planner/graph_planner.py`

**Responsibilities**:
- Build execution DAG
- Optimize task ordering
- Calculate critical path
- Determine scheduling

**Key Methods**:
- `build_execution_graph()` - Create execution plan
- `find_critical_path()` - Critical path analysis
- `optimize_order()` - Task optimization
- `identify_parallel_opportunities()` - Parallelization
- `validate_graph()` - Graph validation

### 4. Constraint Solver
**File**: `planning_engine/constraint_solver/constraint_solver.py`

**Responsibilities**:
- Define and manage constraints
- Validate plans
- Optimize for satisfaction
- Handle conflicts

**Key Methods**:
- `validate_task_graph()` - Full validation
- `optimize_for_constraints()` - Auto-fix
- `create_time_constraint()` - Time rules
- `create_resource_constraint()` - Resource limits

### 5. Resource Planner
**File**: `planning_engine/resource_planner/resource_planner.py`

**Responsibilities**:
- Estimate resource needs
- Allocate resources
- Track usage
- Handle shortages

**Key Methods**:
- `add_resource()` - Register resource
- `estimate_requirements()` - Per-task needs
- `allocate_resources()` - Assignment
- `release_resources()` - Cleanup
- `find_available_slot()` - Scheduling

### 6. Scheduler
**File**: `planning_engine/scheduler/scheduler.py`

**Responsibilities**:
- Schedule tasks for execution
- Handle priorities
- Support parallel execution
- Async scheduling

**Key Methods**:
- `schedule()` - Main scheduling
- `_schedule_sequential()` - Linear
- `_schedule_parallel()` - Concurrent
- `_schedule_pipeline()` - Assembly line
- `_schedule_hybrid()` - Mixed mode

### 7. Risk Analyzer
**File**: `planning_engine/risk_analyzer/risk_analyzer.py`

**Responsibilities**:
- Identify potential risks
- Assess probability/impact
- Generate mitigation
- Create contingency

**Key Methods**:
- `analyze()` - Full risk analysis
- `_identify_task_risks()` - Per-task
- `_identify_systemic_risks()` - Cross-cutting
- `_generate_mitigation()` - Strategy

### 8. Alternative Planner
**File**: `planning_engine/alternative_planner/alternative_planner.py`

**Responsibilities**:
- Generate alternative plans
- Compare options
- Rank by score

### 9. Plan Validator
**File**: `planning_engine/alternative_planner/alternative_planner.py`

**Responsibilities**:
- Verify plan correctness
- Check dependencies
- Detect issues

### 10. Execution Strategy Selector
**File**: `planning_engine/alternative_planner/alternative_planner.py`

**Responsibilities**:
- Select optimal strategy
- Sequential/Parallel/Pipeline/Hybrid

### 11. Replanning Engine
**File**: `planning_engine/alternative_planner/alternative_planner.py`

**Responsibilities**:
- Handle failures
- Reorder tasks
- Adjust resources

### 12. Progress Tracker
**File**: `planning_engine/alternative_planner/alternative_planner.py`

**Responsibilities**:
- Track execution
- Calculate ETA
- Progress snapshots

### 13. Completion Analyzer
**File**: `planning_engine/alternative_planner/alternative_planner.py`

**Responsibilities**:
- Analyze success/failure
- Extract lessons
- Generate insights

---

## Data Models

### Core Models (`core/models.py`)

| Model | Purpose |
|-------|---------|
| `Goal` | Represents a goal with priority, status |
| `GoalTree` | Hierarchical goal structure |
| `Task` | Executable task with dependencies |
| `TaskGraph` | Directed Acyclic Graph of tasks |
| `ExecutionGraph` | Scheduled execution plan |
| `Resource` | Resource definition and allocation |
| `Risk` | Risk with probability and impact |
| `Plan` | Complete execution plan |

### Enums

| Enum | Values |
|------|--------|
| `GoalStatus` | PENDING, ACTIVE, COMPLETED, FAILED, BLOCKED |
| `GoalPriority` | CRITICAL, HIGH, MEDIUM, LOW |
| `TaskStatus` | PENDING, READY, RUNNING, COMPLETED, FAILED |
| `TaskType` | ACTION, QUERY, VERIFICATION, ANALYSIS, SYNTHESIS |
| `ExecutionStrategyType` | SEQUENTIAL, PARALLEL, PIPELINE, HYBRID |
| `RiskLevel` | LOW, MEDIUM, HIGH, CRITICAL |

---

## Runtime Flow

```
1. Input: Reasoning Result
   ↓
2. Goal Creation
   - Extract main goal from reasoning
   - Create sub-goals from reasoning steps
   ↓
3. Task Decomposition
   - Convert goals to tasks
   - Detect dependencies
   - Identify parallelization
   ↓
4. Graph Building
   - Create execution DAG
   - Calculate critical path
   - Optimize order
   ↓
5. Risk Analysis
   - Identify task risks
   - Identify systemic risks
   - Generate mitigations
   ↓
6. Validation
   - Check for cycles
   - Verify dependencies
   - Check constraints
   ↓
7. Strategy Selection
   - Analyze task graph
   - Select best strategy
   ↓
8. Alternative Generation
   - Create backup plans
   - Rank by score
   ↓
9. Output: Planning Result
   - Complete execution plan
   - Risk analysis
   - Alternatives
```

---

## Dependency Graph

```
PlanningEngine
├── GoalManager
│   └── Goal, GoalTree
├── TaskDecomposer
│   └── Task, TaskGraph
├── GraphPlanner
│   └── ExecutionGraph
├── ConstraintSolver
│   └── Constraint validation
├── ResourcePlanner
│   └── Resource, ResourceAllocation
├── Scheduler
│   └── Execution scheduling
├── RiskAnalyzer
│   └── Risk, RiskAnalysis
├── AlternativePlanner
│   └── AlternativePlan
├── PlanValidator
│   └── PlanValidation
├── ExecutionStrategySelector
│   └── Strategy types
├── ReplanningEngine
│   └── Failure handling
├── ProgressTracker
│   └── ProgressSnapshot
└── CompletionAnalyzer
    └── CompletionAnalysis
```

---

## Extension Points

### 1. Custom Strategies
Implement `ExecutionStrategyType` variants by extending `Scheduler`.

### 2. Custom Risk Patterns
Add patterns to `RiskAnalyzer._risk_patterns`.

### 3. Custom Constraints
Add constraint types to `ConstraintSolver`.

### 4. Plugin System
Extend `Plugin` base class for custom components.

---

## Usage Example

```python
from planning_engine import get_planning_engine

# Initialize
engine = await get_planning_engine().initialize()

# Create reasoning result (from Reasoning Engine)
reasoning_result = {
    "answer": "Build a recommendation system",
    "reasoning_steps": [
        {"step": "Design data pipeline"},
        {"step": "Implement model"},
        {"step": "Deploy service"}
    ],
    "title": "Recommendation System"
}

# Plan
result = await engine.plan(reasoning_result)

print(f"Goals: {result.total_goals}")
print(f"Tasks: {result.total_tasks}")
print(f"Strategy: {result.execution_strategy}")
print(f"Confidence: {result.confidence}")
```

---

## Production Readiness

| Criterion | Status |
|-----------|--------|
| All components implemented | ✅ |
| Async/await support | ✅ |
| Pydantic models | ✅ |
| Registry pattern | ✅ |
| Dependency injection | ✅ |
| No stubs/placeholders | ✅ |
| Unit tests | ✅ |
| Production ready | ✅ |

---

## Files Structure

```
planning_engine/
├── __init__.py
├── planning_engine.py          # Main engine
├── core/
│   ├── __init__.py
│   ├── models.py               # Pydantic models
│   └── base.py                # Base classes
├── goal_manager/
│   └── goal_manager.py         # Goal management
├── task_decomposer/
│   └── task_decomposer.py     # Task decomposition
├── graph_planner/
│   └── graph_planner.py       # DAG building
├── constraint_solver/
│   └── constraint_solver.py   # Constraint handling
├── resource_planner/
│   └── resource_planner.py     # Resource management
├── scheduler/
│   └── scheduler.py           # Task scheduling
├── risk_analyzer/
│   └── risk_analyzer.py        # Risk analysis
└── alternative_planner/
    └── alternative_planner.py  # Alternatives & more
```

---

**END OF ARCHITECTURE DOCUMENT**
