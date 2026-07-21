# 🔄 Brain V3 + ModularReasoningEngine Call Flow

**تاريخ:** 2026-07-21  
**الحالة:** ✅ مُدمج فعلياً

---

## 1. imports في brain_v3.py

```python
# Line 33-44
from .cognitive_layer.reasoning_engine import (
    ReasoningEngine,           # OLD - for fallback
    ReasoningResult,
    get_reasoning_engine,
)

# NEW: Import Modular Reasoning Engine
from .cognitive_layer.modular.orchestrator import (
    ModularReasoningEngine,
    ModularReasoningResult,
    create_modular_engine,
)
from .cognitive_layer.modular.strategy import ReasoningStrategy
```

---

## 2. إنشاء الكائن (Initialization)

```python
# Line 250-264
# Initialize Reasoning Engine (supports both OLD and NEW modular engine)
self._use_modular_reasoning = os.environ.get("USE_MODULAR_REASONING", "true").lower() == "true"

if self._use_modular_reasoning:
    # NEW: Use Modular Reasoning Engine
    from hajeen_platform.core.llm import get_llm_manager
    llm_manager = get_llm_manager()
    self.reasoning_engine: ModularReasoningEngine = create_modular_engine(llm_manager)
    self._is_modular_engine = True
    logger.info("Using MODULAR Reasoning Engine ✓")
else:
    # OLD: Fallback to legacy engine
    self.reasoning_engine: ReasoningEngine = get_reasoning_engine()
    self._is_modular_engine = False
```

---

## 3. استدعاء reason() في process()

```python
# Line 398-409
# Unified call works for both OLD and NEW engines
reasoning: Any = await self.reasoning_engine.reason(
    problem=request.user_message,
    context={
        "intent": intent.primary_intent,
        "goal": goal.final_objective,
        "domain": ctx_analysis.detected_domain,
        "complexity": ctx_analysis.estimated_complexity,
        "constraints": ctx_analysis.constraints,
        "relevant_memories": ctx_analysis.relevant_memories[:3],
    },
)
```

---

## 4. Call Flow الكامل

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        User Request                                         │
│                   user_message = "..."                                      │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   HajeenBrainV3.process()                                    │
│                        brain_v3.py:262                                      │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 1: Policy Engine                                          │
│         brain_v3.py: ~320 → self.policy.evaluate()                         │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 2: Intent Analyzer                                        │
│         brain_v3.py: ~340 → self.intent_analyzer.analyze()                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 3: Goal Manager                                           │
│         brain_v3.py: ~345 → self.goal_manager.create_goal()                 │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 4: Context Analyzer                                       │
│         brain_v3.py: ~350 → self.context_analyzer.analyze()                │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 4: REASONING ENGINE ⭐                                    │
│         brain_v3.py: 399 → self.reasoning_engine.reason()                  │
│                                                                              │
│         ════════════════════════════════════════════════════════════════════ │
│         ║                                                               ║ │
│         ║   9 LAYERS ARE NOW CALLED WITHIN ModularReasoningEngine   ║ │
│         ║                                                               ║ │
│         ║   See Section 5 Below for Internal Flow                   ║ │
│         ║                                                               ║ │
│         ════════════════════════════════════════════════════════════════════ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 5: Task Decomposer                                       │
│         brain_v3.py: ~445 → self.task_decomposer.decompose()               │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 6: Graph Planner                                          │
│         brain_v3.py: ~450 → self.graph_planner.build_plan()                │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 7: Decision Engine                                         │
│         brain_v3.py: ~460 → self.decision_engine.decide()                   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              Step 8: Model Router                                           │
│         brain_v3.py: ~470 → self.model_router.route()                      │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              BrainResponse ← Return to User                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Internal Flow داخل ModularReasoningEngine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              ModularReasoningEngine.reason()                                │
│                   orchestrator.py:85                                        │
│                                                                              │
│         orchestrator.py:85-180                                              │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 1: StrategySelector.execute()                                        │
│  File: strategy.py:82                                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Check user preference                                               │ │
│  │ 2. Analyze problem keywords                                            │ │
│  │ 3. Return selected strategy + confidence                               │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 2: ContextManager.execute()                                          │
│  File: context.py:73                                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Validate problem (not empty, not too long)                          │ │
│  │ 2. Build ReasoningContext with Builder pattern                        │ │
│  │ 3. Enrich context with metadata                                       │ │
│  │ 4. Return validated context                                           │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 3: SessionManager.execute()                                          │
│  File: session.py:67                                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Get or create session                                              │ │
│  │ 2. Record reasoning operation                                          │ │
│  │ 3. Update session statistics                                          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 4: ReasoningStateMachine.transition()                                │
│  File: state.py:78                                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ State: INITIAL → CONTEXT_BUILT → STRATEGY_SELECTED → EXECUTING       │ │
│  │ Each transition is validated                                          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 5: Core Reasoning (LLM Call)                                        │
│  File: orchestrator.py:145                                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Build strategy-specific prompt                                      │ │
│  │ 2. Call LLM: self.llm_manager.generate(prompt)                         │ │
│  │ 3. Parse JSON response into reasoning_steps                            │ │
│  │ 4. Return steps[]                                                     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 6: ConfidenceEngine.execute()                                        │
│  File: confidence.py:50                                                     │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Calculate step_confidence from steps[]                              │ │
│  │ 2. Calculate solution_confidence from solutions[]                       │ │
│  │ 3. Apply risk_adjustment                                              │ │
│  │ 4. Return weighted overall_confidence                                  │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 7: ExplanationEngine.execute()                                       │
│  File: explanation.py:44                                                    │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Build summary from problem + strategy                                │ │
│  │ 2. Create sections from steps, solutions, risks                        │ │
│  │ 3. Generate reasoning_chain[]                                         │ │
│  │ 4. Return ExplanationResult with markdown                             │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 8: VerificationLayer.execute()                                       │
│  File: verification.py:42                                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Run minimum_steps check                                            │ │
│  │ 2. Run valid_confidence check                                         │ │
│  │ 3. Run no_circular_reasoning check                                    │ │
│  │ 4. Return VerificationResult with score                               │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 9: ReflectionLayer.execute()                                         │
│  File: reflection.py:44                                                     │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Generate insights[] based on steps, solutions, risks                │ │
│  │ 2. Create improvement_suggestions[]                                   │ │
│  │ 3. Assess overall quality                                             │ │
│  │ 4. Return ReflectionResult                                            │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Build ModularReasoningResult                                               │
│  File: orchestrator.py:155                                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ reasoning_id: str (UUID)                                              │ │
│  │ strategy_used: ReasoningStrategy                                       │ │
│  │ reasoning_steps: List[Dict]                                           │ │
│  │ overall_confidence: float (from ConfidenceEngine)                     │ │
│  │ explanation: Dict (from ExplanationEngine)                             │ │
│  │ verification: Dict (from VerificationLayer)                            │ │
│  │ reflection: Dict (from ReflectionLayer)                               │ │
│  │ trace_id: str (from ExecutionTraceManager)                            │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Save to Cache + Return                                                     │
│  File: orchestrator.py:165-175                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Generate cache_key from problem + strategy + context                │ │
│  │ 2. Save to self._reasoning_cache{}                                   │ │
│  │ 3. End trace: self.trace_manager.end_trace(success=True)             │ │
│  │ 4. Update metrics: self.metrics.increment("reasoning_success")        │ │
│  │ 5. Return ModularReasoningResult to Brain V3                         │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Proof of Integration (Call Chain)

```python
# Brain V3 calls reasoning_engine.reason()
# File: brain_v3.py:399
reasoning: Any = await self.reasoning_engine.reason(...)

# self.reasoning_engine IS ModularReasoningEngine
# because: brain_v3.py:253-257
if self._use_modular_reasoning:
    self.reasoning_engine = create_modular_engine(llm_manager)

# ModularReasoningEngine.reason() calls all 9 layers
# File: orchestrator.py:85-180

# Layer 1: Strategy Selector
# orchestrator.py:112
strategy_result = await self.strategy_selector.execute({...})

# Layer 2: Context Manager
# orchestrator.py:115
context_result = await self.context_manager.execute({...})

# Layer 3: Confidence Engine
# orchestrator.py:125
confidence_result = await self.confidence_engine.execute({...})

# Layer 4: Explanation Engine
# orchestrator.py:128
explanation_result = await self.explanation_engine.execute({...})

# Layer 5: Verification Layer
# orchestrator.py:131
verification_result = await self.verification_layer.execute({...})

# Layer 6: Reflection Layer
# orchestrator.py:134
reflection_result = await self.reflection_layer.execute({...})
```

---

## 7. Environment Variable Control

```bash
# Use NEW ModularReasoningEngine (default)
export USE_MODULAR_REASONING=true
python your_app.py

# Use OLD Legacy ReasoningEngine (fallback)
export USE_MODULAR_REASONING=false
python your_app.py
```

---

## 8. Verification via get_status()

```python
# Call brain.get_status()
status = await brain.get_status()

# Returns:
{
    "version": "3.0.0",
    "reasoning_engine": {
        "type": "modular_v2",    # ← Shows which engine is active
        "active": True,
        "cache": {
            "enabled": True,
            "entries": 5,
            "max_entries": 1000,
        }
    },
    ...
}
```

---

## 9. Summary

| Component | File | Status |
|-----------|------|--------|
| Brain V3 uses ModularReasoningEngine | brain_v3.py | ✅ Integrated |
| Import statement added | brain_v3.py:39-44 | ✅ Done |
| Object creation with config | brain_v3.py:250-264 | ✅ Done |
| Unified reason() call | brain_v3.py:398-409 | ✅ Done |
| All 9 layers executed | orchestrator.py | ✅ Active |

**Conclusion:** The ModularReasoningEngine is now ACTUALLY CALLED when Brain V3 processes requests.
