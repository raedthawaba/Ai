# Hajeen Migration Plan - Production Baseline v1.0

**Date:** 2026-07-21
**Status:** PLANNING PHASE

---

## 1. Architecture Order Issues

### Current Order (PROBLEMATIC)
```
1. استعادة سياق الجلسة (Session Restore)
2. Policy Engine
3. Intent Analyzer
4. Planning Engine ← OUT OF ORDER (called BEFORE Context & Reasoning)
5. Context Analyzer
6. Reasoning Engine
7. Task Decomposer (sub-component of Planning)
8. Graph Planner (sub-component of Planning)
9. Decision Engine
10. State Machine
11. Model Router/Execution
12. Performance Recording
13. Knowledge Distillation (Learning)
14. Memory Update
15. Sovereignty Layer
16. Self Reflection (Learning)
17. Lifecycle End
```

### Expected Order (CORRECT)
```
1. Policy
2. Intent
3. Context
4. Memory/Knowledge
5. Reasoning
6. Planning
7. Decision
8. Model Router
9. Execution
10. Reflection
11. Learning
```

### Issues Found

| Issue | Severity | Description |
|-------|----------|-------------|
| ISSUE-1 | HIGH | Planning Engine called BEFORE Context and Reasoning |
| ISSUE-2 | HIGH | Memory/Knowledge accessed late instead of early |
| ISSUE-3 | MEDIUM | Task Decomposer & Graph Planner separate from Planning |
| ISSUE-4 | LOW | State Machine called separately |
| ISSUE-5 | MEDIUM | Learning happens at end instead of incrementally |

### Recommended Fix (Phase 2)

**Do NOT modify directly** - This is a planning document.

The correct order should be:
```
1. Session Restore (implicit)
2. Policy (security check)
3. Intent (understand user goal)
4. Context + Memory/Knowledge (build context)
5. Reasoning (analyze problem)
6. Planning (create execution plan)
   6a. Task Decomposition
   6b. Graph Building
7. Decision (resource allocation)
8. Model Router (select models)
9. Execution (run plan)
10. Reflection (evaluate result)
11. Learning (update memory/knowledge)
```

---

## 2. Version Baseline

### Official Files (Active)

| File/Directory | Status | Purpose |
|---------------|--------|---------|
| brain.py | ACTIVE | Main entry point |
| brain_v3.py | ACTIVE | Production pipeline |
| contracts/ | ACTIVE | Shared data models |
| cognitive_layer/ | ACTIVE | Intent, Context, Reasoning |
| planning_engine.py | ACTIVE | Core planning |
| decision_engine.py | ACTIVE | Decision making |
| model_router.py | ACTIVE | Model selection |
| memory/ | ACTIVE | Memory management |
| knowledge/ | ACTIVE | Knowledge management |
| policy/ | ACTIVE | Policy engine |
| reflection/ | ACTIVE | Self-reflection |
| improvement/ | ACTIVE | Autonomous improvement |
| learning/ | ACTIVE | Continuous learning |
| metrics/ | ACTIVE | Metrics collection |
| sovereignty/ | ACTIVE | Sovereignty layer |
| state_machine.py | ACTIVE | State management |

### Archived Files (Reference Only - DO NOT DELETE)

| File | Reason |
|------|--------|
| graph_planner_v3.py | Versioned duplicate - archived |
| task_decomposer_v3.py | Versioned duplicate - archived |
| model_router_v3.py | Versioned duplicate - archived |
| memory_fabric_v3.py | Versioned duplicate - archived |
| knowledge_graph_v3.py | Versioned duplicate - archived |
| multi_agent_system_v3.py | Versioned duplicate - archived |

---

## 3. Dependency Cleanup

### Imported Modules in brain_v3.py

```
✅ cognitive_layer.context_analyzer
✅ cognitive_layer.intent_analyzer
✅ cognitive_layer.reasoning_engine
✅ decision_engine
✅ goal_manager
✅ graph_planner
✅ improvement.autonomous_improvement
✅ knowledge.knowledge_distillation
✅ knowledge.knowledge_graph
✅ memory.memory_fabric
✅ metrics.model_performance_db
✅ model_router
✅ multi_model
✅ planning_engine
✅ policy.policy_engine
✅ reflection.self_evolution
✅ reflection.self_reflection
✅ sovereignty.sovereignty_layer
✅ state_machine
✅ task_decomposer
```

### Potential Orphan Files

These files exist but are NOT imported by the main pipeline:

| File | Status | Action |
|------|--------|--------|
| llm_analyzer.py | ORPHAN | Keep - used by goal_manager |
| production_infra.py | ORPHAN | Keep - for production deployment |
| autonomous_planner.py | ORPHAN | Keep - future feature |
| multi_model.py | ACTIVE | Used in brain_v3 |

---

## 4. Proposed Final Structure

```
brain/
├── __init__.py
├── brain.py                 # Main entry point (renamed from brain_v3.py in Phase 2)
├── contracts/              # Shared data contracts
│   ├── __init__.py
│   ├── base.py
│   ├── brain_request.py
│   ├── brain_response.py
│   ├── reasoning_contract.py
│   ├── planning_contract.py
│   ├── decision_contract.py
│   └── execution_contract.py
├── cognitive_layer/        # Cognitive processing
│   ├── __init__.py
│   ├── intent_analyzer.py
│   ├── context_analyzer.py
│   └── reasoning_engine.py
├── planning_engine.py       # Core planning
├── decision_engine.py       # Decision making
├── model_router.py         # Model selection
├── memory/                 # Memory management
│   └── memory_fabric.py
├── knowledge/               # Knowledge management
│   ├── knowledge_graph.py
│   └── knowledge_distillation.py
├── policy/                  # Policy engine
│   └── policy_engine.py
├── state_machine.py         # State management
├── execution_trace.py       # Trace logging
├── metrics/                 # Metrics
│   └── model_performance_db.py
├── reflection/              # Self-reflection
│   ├── self_reflection.py
│   └── self_evolution.py
├── improvement/             # Autonomous improvement
│   └── autonomous_improvement.py
├── learning/                # Continuous learning
├── sovereignty/             # Sovereignty layer
│   └── sovereignty_layer.py
└── api/                     # API routes
    └── brain_router.py

# Archived (Reference Only - DO NOT DELETE)
archived/
├── graph_planner_v3.py
├── task_decomposer_v3.py
├── model_router_v3.py
├── memory_fabric_v3.py
├── knowledge_graph_v3.py
└── multi_agent_system_v3.py
```

---

## 5. Action Items (Phase 2)

| # | Action | Priority | Status |
|---|--------|----------|--------|
| 1 | Rename brain_v3.py to brain.py | HIGH | PENDING |
| 2 | Reorder pipeline execution | HIGH | PENDING |
| 3 | Move Task Decomposer into Planning Engine | MEDIUM | PENDING |
| 4 | Move Graph Planner into Planning Engine | MEDIUM | PENDING |
| 5 | Integrate Memory/Knowledge earlier in pipeline | HIGH | PENDING |
| 6 | Move Learning to be incremental | MEDIUM | PENDING |
| 7 | Create HajeenBrain main class | HIGH | PENDING |
| 8 | Contract validation for all engines | HIGH | PENDING |

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Breaking existing tests when reordering | Create integration test suite first |
| Losing functionality during refactor | Keep archived files for reference |
| Performance regression | Benchmark before and after changes |

---

## 7. Success Criteria

1. ✅ All engines use contracts for data transfer
2. ✅ Execution order matches expected architecture
3. ✅ No raw dict passing between engines
4. ✅ brain_v3.py renamed to brain.py
5. ✅ All versioned duplicates archived
6. ✅ HajeenBrain class as single entry point
7. ✅ All tests passing

---

## Notes

- **DO NOT DELETE** any archived files
- **DO NOT MODIFY** execution order without creating tests first
- **Phase 1 (this phase)** = Baseline establishment
- **Phase 2** = Architecture correction and refactoring
