# Hajeen AI — Architecture Documentation
## منصة الذكاء الاصطناعي السيادية

---

## نظرة عامة

Hajeen AI هي منصة ذكاء اصطناعي سيادية (Sovereign AI Platform) مصممة لتكون العقل الحقيقي للنظام. تمر جميع الطلبات عبر طبقات إدراكية متعددة قبل أن تصل إلى أي نموذج أو أداة.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Hajeen Brain V3                          │
│                    (العقل المدبّر المركزي)                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Policy Engine    →  فحص الأمان والأخلاقيات                  │
│  2. Intent Analyzer  →  استخراج النية الحقيقية                  │
│  3. Goal Analyzer    →  تحويل النية إلى أهداف                   │
│  4. Context Analyzer →  تحليل السياق والذاكرة الدلالية          │
│  5. Reasoning Engine →  الاستدلال العميق (Chain/Tree of Thought) │
│  6. Task Decomposer  →  تفكيك الأهداف إلى مهام                  │
│  7. Graph Planner    →  بناء DAG للتنفيذ                         │
│  8. Decision Engine  →  اختيار النموذج والأدوات                 │
│  9. Model Router     →  توجيه للنموذج المناسب                   │
│  10. Execution       →  تنفيذ متوازٍ أو تسلسلي                  │
│  11. Distillation    →  استخلاص المعرفة                         │
│  12. Self Reflection →  التقييم الذاتي                          │
│  13. Sovereignty     →  تسجيل الاستقلالية                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## طبقات النظام

### 1. Hajeen Brain (العقل المركزي)
**الموقع:** `hajeen_platform/brain/brain_v3.py`

- يستقبل كل طلب ويوجهه عبر 12+ طبقة
- لا يوجد shortcut أو bypass لأي طبقة
- يحتفظ بـ `ExecutionTrace` لكل طلب لأغراض المراقبة
- إصدار واحد نشط في الوقت ذاته (Singleton)

**المبدأ الذهبي:**
> أي نموذج خارجي = Temporary Expert فقط. كل معرفة تُكتسب من الخارج تتحول تدريجياً لمعرفة داخلية.

---

### 2. Cognitive Layer (الطبقة المعرفية)
**الموقع:** `hajeen_platform/brain/cognitive_layer/`

#### 2.1 Intent Analyzer
- **الملف:** `intent_analyzer.py`
- **الهدف:** استخراج النية الحقيقية بالاستدلال، وليس مطابقة الكلمات
- **المخرجات:** `Intent` (category, primary_intent, confidence, reasoning)
- **الفئات:** `CODE_DEVELOPMENT`, `ANALYSIS`, `PLANNING`, `CONVERSATION`, ...

#### 2.2 Context Analyzer
- **الملف:** `context_analyzer.py`
- **الهدف:** تحليل السياق الكامل + البحث الدلالي في الذاكرة
- **الميزات الرئيسية:**
  - Semantic Memory Search بـ cosine similarity على embeddings
  - تحليل LLM لتحديد المجال ومستوى الخبرة والتعقيد
  - استرجاع من Long-term Memory + Semantic Memory

#### 2.3 Reasoning Engine
- **الملف:** `reasoning_engine.py`
- **الاستراتيجيات:** Chain of Thought, Tree of Thought, First Principles, Multi-Perspective
- **المخرجات:** `ReasoningResult` (steps, risks, solution_options, recommended_solution)

---

### 3. Decision Engine (محرك القرار)
**الموقع:** `hajeen_platform/brain/decision_engine_v3.py`

يختار بذكاء:
- النموذج المناسب (محلي vs سحابي)
- الأدوات (RAG, Web Search, Code Execution)
- استراتيجية التنفيذ (متوازٍ, تسلسلي, متعدد النماذج)

**مصادر بيانات الجودة (بالأولوية):**
1. `ModelPerformanceDB` — بيانات الأداء الحقيقي
2. `model_registry.json` — سجل النماذج المدرَّبة محلياً
3. قيم مرجعية موثقة لكل نموذج معروف

---

### 4. Model Router (موجه النماذج)
**الموقع:** `hajeen_platform/brain/model_router_v3.py`

- يدعم Ollama (محلي), OpenAI, Anthropic, Qwen
- Fallback آلي عند فشل النموذج الأول
- تسجيل أداء كل طلب في `ModelPerformanceDB`

---

### 5. Memory Fabric (نسيج الذاكرة)
**الموقع:** `hajeen_platform/brain/memory/memory_fabric.py`

```
MemoryFabric
├── SessionMemory      — ذاكرة الجلسة الحالية (RAM)
├── ConversationMemory — نافذة المحادثة (آخر N رسالة)
├── LongTermMemory     — تخزين دائم على القرص (JSON)
├── SemanticMemory     — ذاكرة دلالية + بحث بالـ embeddings
├── EpisodicMemory     — تسجيل الأحداث والنتائج
├── ProceduralMemory   — تخزين الإجراءات المتعلَّمة
└── AgentMemory        — ذاكرة خاصة بكل Agent
```

---

### 6. Knowledge Graph (رسم بياني للمعرفة)
**الموقع:** `hajeen_platform/brain/knowledge/knowledge_graph.py`

- **الكيانات:** Person, Project, Concept, Tool, Event, File, Agent
- **العلاقات:** USES, DEPENDS_ON, RELATED_TO, IS_PART_OF, PRODUCES
- يدعم الاستعلام والاستدلال على العلاقات

---

### 7. Multi-Agent System (نظام متعدد الوكلاء)
**الموقع:** `hajeen_platform/brain/multi_agent_system_v3.py`

**الوكلاء المتاحة:**
- `ResearchAgent` — بحث وتحليل المعلومات
- `CodingAgent` — توليد وتحليل الكود
- `PlanningAgent` — التخطيط الاستراتيجي
- `EvaluationAgent` — تقييم الجودة
- `MemoryAgent` — إدارة الذاكرة
- `TrainingAgent` — التدريب المستمر

يتولى `HajeenBrain` إدارتهم وتنسيقهم.

---

### 8. Continuous Learning Pipeline (التعلم المستمر)
**الموقع:** `hajeen_platform/brain/learning/continuous_learning.py`

```
Raw Data
    ↓ Collection
    ↓ Cleaning (إزالة الفارغ والقصير)
    ↓ Deduplication (Hash + Cosine Similarity على Embeddings)
    ↓ Quality Validation (threshold: 0.6)
    ↓ Filtering (كشف المحتوى الضار)
    ↓ Ranking (ترتيب حسب الجودة)
    ↓ Human Approval (اختياري في الإنتاج)
    ↓ Dataset Builder (JSONL)
    ↓ Training Queue (قائمة انتظار دائمة)
    ↓ Fine-Tuning (LoRA/PEFT + HuggingFace)
    ↓ Evaluation (Perplexity + Accuracy + BLEU)
    ↓ Deployment (Model Registry)
    ↓ Rollback (إذا فشل التقييم)
```

---

### 9. Self Reflection & Evolution (التقييم الذاتي والتطور)

**Self Reflection** (`reflection/self_reflection.py`):
- يقيّم كل مهمة: الخطة، القرار، اختيار النموذج، الأداء
- يولّد تقارير مخزنة في `storage_data/brain/`

**Self Evolution** (`reflection/self_evolution.py`):
- يحلل تقارير الانعكاس الذاتي
- يقترح تحسينات على السياسات والاستراتيجيات
- يُطبّق التغييرات بطريقة آمنة مدروسة

---

### 10. Monitoring & Observability (المراقبة)
**الموقع:** `monitoring/`

- **Prometheus:** جمع المقاييس (latency, throughput, error_rate)
- **Grafana:** لوحات مرئية جاهزة
- **Worker Monitor:** مراقبة صحة الـ workers
- **ExecutionTrace:** تتبع كل طلب عبر جميع الطبقات

---

### 11. Security (الأمان)
**الموقع:** `hajeen_platform/security/`

- **Authentication & Authorization:** JWT + RBAC
- **Rate Limiting:** حماية من إساءة الاستخدام
- **Encryption:** تشفير البيانات الحساسة
- **Audit Logs:** سجل كامل لكل العمليات
- **Secrets Management:** إدارة مركزية للمفاتيح

---

### 12. Scalability (التوسعية)
**الموقع:** `hajeen_platform/workers/`

- **Celery + Redis:** معالجة الطلبات الثقيلة بشكل غير متزامن
- **Distributed Workers:** CPU + GPU workers منفصلة
- **Priority Queue:** أولويات للطلبات الحرجة
- **Load Balancing:** توزيع الحمل على الـ workers
- **Backpressure:** حماية النظام من الحمل الزائد

---

## قرارات معمارية رئيسية

| القرار | السبب |
|--------|-------|
| كل طلب يمر عبر Brain V3 إلزامياً | ضمان المرور عبر الطبقة المعرفية دائماً |
| LoRA بدلاً من Full Fine-Tuning | كفاءة في الذاكرة وسرعة التدريب |
| Cosine Similarity للـ Deduplication | دقة أعلى من مطابقة النص البسيطة |
| Three-tier Quality Lookup في Decision Engine | تحسين قرارات اختيار النموذج بالبيانات الفعلية |
| Model Registry مستقل | تتبع النماذج ودعم الـ Rollback الآمن |
| Deferred Training عند غياب GPU | النظام لا يتوقف، يحفظ الـ config للتدريب لاحقاً |
