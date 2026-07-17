# Hajeen AI — Data Flow Documentation
## تدفق البيانات

---

## نظرة عامة

```
┌─────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────────┐
│  User   │───▶│  API     │───▶│ Brain V3    │───▶│  LLM Model   │
│         │    │  Layer   │    │ (12 layers) │    │  (Local/API) │
└─────────┘    └──────────┘    └─────────────┘    └──────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
             ┌──────────┐     ┌──────────┐     ┌──────────────┐
             │ Memory   │     │Knowledge │     │  Learning    │
             │ Fabric   │     │  Graph   │     │  Pipeline    │
             └──────────┘     └──────────┘     └──────────────┘
```

---

## تدفق البيانات في كل مكون

### 1. طلب المستخدم (Input)
```
HTTP POST /api/v1/brain/chat
Content-Type: application/json
{
  "message": string,
  "session_id": string,
  "user_id": string?,
  "stream": boolean,
  "max_tokens": int,
  "temperature": float,
  "force_model": string?
}
```

### 2. Policy Engine
```
Input:  { query, session_id, estimated_tokens, request_type }
Output: PolicyDecision { blocked: bool, final_decision: str, rule_results: list }
```

### 3. Intent Analyzer
```
Input:  { user_message: str, context: dict }
        → LLM Prompt (structured)
        ← LLM JSON Response
Output: Intent {
  intent_id, category, primary_intent,
  secondary_intents, implicit_requirements,
  confidence, reasoning
}
```

### 4. Goal Manager
```
Input:  { user_message: str, context: { intent: str, ... } }
        → LLM Prompt
        ← LLM JSON Response
Output: Goal {
  goal_id, final_objective, sub_goals,
  complexity, domain, required_tools, confidence
}
```

### 5. Context Analyzer
```
Input:  { user_message: str, session_id: str, additional_context: dict }
        → EmbeddingManager.embed(user_message) → [float × 768]
        → LongTermMemory.list_keys() → [str]
        → For each key: embed(entry_content) → cosine_similarity
        → SemanticMemory.search(query, top_k=3)
        → LLM Analysis (domain, complexity, constraints)
Output: ContextAnalysis {
  analysis_id, detected_domain, domain_expertise_level,
  estimated_complexity, relevant_memories (top 7),
  constraints, priorities, time_sensitivity, confidence
}
```

### 6. Reasoning Engine
```
Input:  { problem: str, context: { domain, complexity, constraints, memories } }
        → LLM Multi-step Reasoning Prompt
        ← Structured JSON with steps, risks, solutions
Output: ReasoningResult {
  result_id, strategy, reasoning_steps, missing_information,
  risks, solution_options, recommended_solution, confidence
}
```

### 7. Task Decomposer
```
Input:  Goal object
        → LLM Decomposition Prompt
        ← { objective, tasks: [{ id, description, dependencies }] }
Output: DecompositionPlan {
  plan_id, goal_id, tasks, dependencies
}
```

### 8. Graph Planner
```
Input:  DecompositionPlan
Output: ExecutionGraph (DAG) {
  graph_id, nodes: [Task], edges: [Dependency],
  topological_order: [task_id]
}
```

### 9. Decision Engine V3
```
Input:  { goal, context, execution_graph }
        → _get_model_quality(model_id):
             1. ModelPerformanceDB.get_model_statistics(model_id)
             2. model_registry.json (if hajeen-* model)
             3. Known Quality Table
        → _score_candidates(candidates) → sorted list
Output: Decision {
  decision_id, model_id, use_rag, use_web_search,
  use_multi_model, resource_type, reasoning
}
```

### 10. Model Router
```
Input:  { model_id, prompt, max_tokens, temperature }
Output: RouteResult {
  route_id, model_id,
  generate(prompt) → str
}
```

### 11. Knowledge Distillation
```
Input:  { question, answer, model_id, quality_score }
        → استخراج: steps, reasoning, tools_used, success_factors
Output: KnowledgeEntry → stored in KnowledgeGraph + LongTermMemory
```

### 12. Self Reflection
```
Input:  { task, result, context, execution_trace }
        → تقييم: plan_quality, decision_quality, performance_metrics
Output: ReflectionReport → stored in storage_data/brain/reflections/
```

---

## تدفق بيانات التعلم المستمر

```
Raw Input (List[Dict])
    │
    ├── instruction: str   ← السؤال/التعليمات
    ├── output: str        ← الإجابة/المخرجات
    ├── domain: str        ← المجال (ai, code, general, ...)
    ├── source_model: str  ← النموذج المصدر
    └── quality_score: float ← 0.0 → 1.0

    ↓ After Pipeline

DataSample (cleaned & validated)
    │
    ↓ Storage

JSONL File: storage_data/brain/learning/dataset_{run_id}.jsonl
    │ {"instruction": "...", "output": "...", "domain": "..."}
    │
    ↓ Training

Model Checkpoint: storage_data/brain/learning/model_{run_id}/
    │ config.json, tokenizer.json, adapter_model.safetensors (LoRA)
    │
    ↓ Evaluation

Metrics:
    │ perplexity: float (هدف: < 30)
    │ accuracy: float (هدف: >= 0.60)
    │ bleu: float (مقياس الإشارة)
    │
    ↓ Deployment

model_registry.json:
    │ { "current_active": "hajeen-vYYYYMMDD-{run_id[:8]}",
    │   "models": [...] }
    │
    ↓

active_model.json:
    { "version": "...", "path": "...", "updated_at": ... }
```

---

## تدفق بيانات الذاكرة

```
Session Memory (RAM — مؤقت)
└── Dict[session_id → Dict[key → value]]
    TTL: حياة البرنامج

Conversation Memory (RAM — مؤقت)
└── Dict[session_id → ConversationMemory]
    Window: آخر 20 رسالة

Long-term Memory (القرص — دائم)
└── storage_data/brain/long_memory/
    └── {session_id}_{key_hash}.json
    Format: { content, metadata, stored_at }

Semantic Memory (RAM — مؤقت + بحث)
└── List[MemoryEntry]
    └── { key, content, relevance, metadata, embedding }
    Search: cosine similarity

Episodic Memory (RAM — مؤقت)
└── List[Episode]
    └── { event_type, description, outcome, timestamp }
```

---

## تدفق بيانات الأمان

```
Request
  │
  ├── JWT Token → Verification → User Object
  │                                  │
  │                                  ▼
  │                           RBAC Check
  │                           └── allowed → continue
  │                           └── denied → 403
  │
  ├── Rate Limiter → تحقق الحدود
  │   └── exceeded → 429
  │
  ├── Input Validation (Pydantic/Zod)
  │   └── invalid → 422
  │
  └── Policy Engine → Content Policy Check
      └── blocked → 403 + explanation
```
