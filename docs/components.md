# Hajeen AI — Components Documentation
## توثيق المكونات

---

## Brain Components

### HajeenBrainV3
**الملف:** `brain/brain_v3.py`  
**النوع:** Singleton (Async Lock)  
**الوظيفة:** العقل المركزي الذي يستقبل ويعالج كل طلب

```python
# الاستخدام
from hajeen_platform.brain.brain_v3 import get_brain_v3, BrainRequest

brain = await get_brain_v3()
response = await brain.process(BrainRequest(
    request_id="req_001",
    user_message="ما هو الذكاء الاصطناعي؟",
    session_id="session_123"
))
```

**الخصائص الرئيسية:**
- `VERSION = "3.0.0"`
- `intent_analyzer` — محلل النية
- `context_analyzer` — محلل السياق
- `reasoning_engine` — محرك الاستدلال
- `goal_manager` — مدير الأهداف
- `task_decomposer` — مفكك المهام
- `graph_planner` — مخطط الرسم البياني
- `decision_engine` — محرك القرار
- `model_router` — موجه النماذج
- `memory` — نسيج الذاكرة
- `knowledge_graph` — رسم بياني للمعرفة
- `reflection` — التقييم الذاتي
- `evolution` — التطور الذاتي
- `sovereignty` — طبقة الاستقلالية

---

## Cognitive Layer

### IntentAnalyzer
**الملف:** `brain/cognitive_layer/intent_analyzer.py`

```python
from hajeen_platform.brain.cognitive_layer.intent_analyzer import (
    IntentAnalyzer, Intent, IntentCategory, get_intent_analyzer
)

analyzer = get_intent_analyzer()
intent: Intent = await analyzer.analyze(
    user_message="اكتب دالة Python للفرز",
    context={"session_id": "s1"}
)
print(intent.category)      # IntentCategory.CODE_DEVELOPMENT
print(intent.primary_intent) # "تطوير دالة الفرز"
print(intent.confidence)    # 0.92
```

**IntentCategory:**
- `INFORMATION_SEEKING` — البحث عن معلومات
- `TASK_EXECUTION` — تنفيذ مهمة
- `CREATIVE_GENERATION` — توليد محتوى
- `ANALYSIS_EVALUATION` — تحليل وتقييم
- `CODE_DEVELOPMENT` — تطوير برمجي
- `LEARNING_TRAINING` — التعلم والتدريب
- `PLANNING_STRATEGY` — التخطيط
- `CONVERSATION` — محادثة عامة
- `PROBLEM_SOLVING` — حل المشاكل

---

### ContextAnalyzer
**الملف:** `brain/cognitive_layer/context_analyzer.py`

```python
from hajeen_platform.brain.cognitive_layer.context_analyzer import (
    ContextAnalyzer, ContextAnalysis, get_context_analyzer
)

analyzer = get_context_analyzer()
ctx: ContextAnalysis = await analyzer.analyze(
    user_message="كيف أُحسّن أداء Python؟",
    session_id="session_123",
    user_id="user_456",
    additional_context={"intent": "code_optimization"}
)
print(ctx.detected_domain)         # "code"
print(ctx.estimated_complexity)    # "medium"
print(ctx.relevant_memories)       # قائمة الذكريات ذات الصلة
print(ctx.constraints)             # قيود الطلب
```

**الميزات:**
- Semantic Memory Search: cosine similarity على HF embeddings
- LLM-based domain & complexity analysis
- Long-term Memory integration
- Semantic Memory integration

---

### ReasoningEngine
**الملف:** `brain/cognitive_layer/reasoning_engine.py`

```python
from hajeen_platform.brain.cognitive_layer.reasoning_engine import (
    ReasoningEngine, ReasoningResult, ReasoningStrategy, get_reasoning_engine
)

engine = get_reasoning_engine()
result: ReasoningResult = await engine.reason(
    problem="كيف أُصمّم نظام موزع؟",
    context={"domain": "software", "complexity": "enterprise"}
)
print(result.strategy)              # ReasoningStrategy.CHAIN_OF_THOUGHT
print(result.recommended_solution)  # SolutionOption(title="...")
print(result.risks)                 # قائمة المخاطر
print(result.confidence)            # 0.88
```

**ReasoningStrategy:**
- `CHAIN_OF_THOUGHT` — سلسلة خطوات منطقية
- `TREE_OF_THOUGHT` — شجرة خيارات بديلة
- `DECOMPOSITION` — تفكيك المشكلة
- `ANALOGY` — القياس والتشبيه
- `FIRST_PRINCIPLES` — المبادئ الأولى
- `MULTI_PERSPECTIVE` — وجهات نظر متعددة

---

## Memory System

### MemoryFabric
**الملف:** `brain/memory/memory_fabric.py`

```python
from hajeen_platform.brain.memory.memory_fabric import get_memory_fabric

memory = get_memory_fabric()

# الذاكرة الفورية
session = memory.get_session("session_123")
session.add("key", "value")

# ذاكرة المحادثة
conv = memory.get_conversation("session_123")
conv.add_message("user", "مرحبا")
window = conv.get_window()  # آخر N رسالة

# الذاكرة طويلة الأمد (القرص)
lt = memory.get_long_term_memory("session_123")
lt.store("memory_key", {"content": "معلومة مهمة"})
recalled = lt.recall("memory_key")

# الذاكرة الدلالية (بحث بالتشابه)
memory.semantic.store("محتوى ذاكرة", metadata={})
results = memory.semantic.search("استعلام", top_k=5)

# الذاكرة التجريبية
memory.episodic.record("task_completed", "نجح الفرز", "success")
```

---

## Decision Engine

### DecisionEngineV3
**الملف:** `brain/decision_engine_v3.py`

```python
from hajeen_platform.brain.decision_engine_v3 import get_decision_engine_v3

engine = get_decision_engine_v3()
decision = await engine.decide(goal, context={})

# اختيار النموذج بالأولوية:
# 1. ModelPerformanceDB (بيانات فعلية)
# 2. model_registry.json (نماذج محلية)
# 3. Known Quality Table

quality = await engine._get_model_quality("qwen2.5-7b")  # → 0.79
```

---

## Continuous Learning Pipeline

### ContinuousLearningPipeline
**الملف:** `brain/learning/continuous_learning.py`

```python
from hajeen_platform.brain.learning.continuous_learning import get_learning_pipeline

pipeline = get_learning_pipeline()

# تشغيل pipeline كاملة
run = await pipeline.run([
    {
        "instruction": "ما هو الذكاء الاصطناعي؟",
        "output": "الذكاء الاصطناعي هو...",
        "domain": "ai_concepts",
        "source_model": "gpt-4o",
        "quality_score": 0.92
    }
])

print(run.status)              # PipelineStatus.COMPLETED
print(run.evaluation_results)  # {"perplexity": 8.3, "accuracy": 0.87}
print(run.deployment_info)     # {"model_version": "hajeen-v20240717-..."}

# الموافقة على العينات (إذا كان require_approval=True)
approved = await pipeline.approve_pending()

# الإحصائيات
stats = pipeline.get_stats()
```

**الثوابت:**
- `MIN_QUALITY_SCORE = 0.6`
- `MIN_SAMPLES_FOR_TRAINING = 50`
- `DEDUP_SIMILARITY_THRESHOLD = 0.85`

---

## Workers System

### Celery Workers
**الملف:** `workers/celery_app.py`

```python
from hajeen_platform.workers.celery_app import celery_app

# تشغيل مهمة في الخلفية
result = celery_app.send_task("workers.tasks.inference_tasks.run_inference",
                              args=[request_data])
```

**أنواع الـ Workers:**
- `cpu_worker.py` — لمعالجة النصوص والمنطق
- `gpu_worker.py` — للاستدلال على النماذج الكبيرة
- `embedding_tasks.py` — لحساب الـ embeddings

---

## Security Components

### Auth & RBAC
**الموقع:** `security/`

```python
# التحقق من الهوية
from hajeen_platform.security import verify_token, check_permission

user = await verify_token(jwt_token)
allowed = await check_permission(user, "brain:write")
```

**الأدوار:**
- `admin` — وصول كامل
- `editor` — قراءة وكتابة
- `viewer` — قراءة فقط
- `agent` — للوكلاء الآلية

---

## Monitoring Components

### PrometheusMetrics
**الموقع:** `monitoring/`

**المقاييس الرئيسية:**
- `hajeen_requests_total` — إجمالي الطلبات
- `hajeen_request_latency_seconds` — زمن المعالجة
- `hajeen_model_quality_score` — جودة النموذج
- `hajeen_tokens_used_total` — الرموز المستهلكة
- `hajeen_local_model_ratio` — نسبة النماذج المحلية
- `hajeen_learning_pipeline_runs` — عمليات التدريب
