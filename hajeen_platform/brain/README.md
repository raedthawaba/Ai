# Hajeen Brain V3 — العقل الموحّد لمنصة Hajeen AI

## المفهوم

**HajeenBrainV3** هو أعلى طبقة في منصة Hajeen AI — العقل الوحيد والموحّد.  
لا يصل أي طلب مباشرةً إلى أي نموذج لغوي — كل الطلبات تمر عبر HajeenBrainV3 أولاً.

```
المستخدم
    ↓
HajeenBrainV3 ← العقل الموحّد (Runtime واحد)
    ↓
Policy Engine ← أمان + أخلاقيات + ميزانية
    ↓
Intent Analyzer ← تحليل النية
    ↓
Goal Manager ← فهم الهدف الحقيقي
    ↓
Context Analyzer ← تحليل السياق (UnifiedMemory)
    ↓
Reasoning Engine ← الاستدلال
    ↓
Task Decomposer ← تفكيك إلى مهام صغيرة
    ↓
Graph Planner ← DAG قابل للتوازي
    ↓
Decision Engine ← اختيار النموذج/الأداة
    ↓
Model Router / Multi-Model ← التنفيذ
    ↓
Knowledge Distillation ← استخلاص المعرفة (خلفية)
    ↓
Memory Fabric (UnifiedMemoryInterface) ← حفظ السياق الموحّد
    ↓
Self Reflection ← تقييم ذاتي (خلفية)
    ↓
Cognitive Layer (17 مكوّن) ← التطور المعرفي (خلفية)
    ↓
Sovereignty Layer ← تسجيل الاستقلالية
```

---

## المبدأ الذهبي

> أي نموذج خارجي = **Temporary Expert** فقط.  
> كل معرفة تُكتسب من الخارج تتحول تدريجياً إلى معرفة داخلية يمتلكها Hajeen.  
> **Runtime واحد · Pipeline واحد · Memory واحدة**

---

## المكوّنات الموحّدة

| المكوّن | الملف الرسمي | الوظيفة |
|---------|-------------|---------|
| **HajeenBrainV3** | `brain_v3.py` | العقل الموحّد — المسار الكامل |
| **Policy Engine** | `policy/policy_engine.py` | أمان + أخلاقيات + ميزانية |
| **Intent Analyzer** | `cognitive_layer/intent_analyzer.py` | تحليل نية المستخدم |
| **Context Analyzer** | `cognitive_layer/context_analyzer.py` | فهم السياق |
| **Reasoning Engine** | `cognitive_layer/reasoning_engine.py` | الاستدلال المنطقي |
| **Goal Manager** | `goal_manager.py` | فهم الهدف الحقيقي |
| **Task Decomposer** | `task_decomposer.py` | تفكيك المهام |
| **Graph Planner** | `graph_planner.py` | تخطيط DAG |
| **Decision Engine** | `decision_engine.py` | اختيار النموذج |
| **Model Router** | `model_router.py` | توجيه النماذج |
| **Memory Fabric** | `memory/memory_fabric.py` + `memory/unified_interface.py` | ذاكرة موحّدة |
| **Knowledge Graph** | `knowledge/knowledge_graph.py` | الرسم البياني المعرفي |
| **Self Evolution** | `reflection/self_evolution.py` | التطور الذاتي الموحّد |
| **Cognitive Layer** | `cognitive_layer/` (17 ملف) | الطبقة الإدراكية |

---

## التوحيد المعماري

### ما تم توحيده

| قبل (V2) | بعد (V3 الموحّد) |
|-----------|-----------------|
| `brain.py` (V2) + `brain_v3.py` (V3) | **`brain_v3.py` فقط** — V2 محذوف |
| 3 PromptBuilders منفصلة | **AbstractPromptBuilder** — واجهة موحّدة |
| 4 أنظمة ذاكرة منفصلة | **UnifiedMemoryInterface** — مصدر حقيقة واحد |
| 3 SelfEvolution منفصلة | **reflection/self_evolution.py** — نسخة واحدة |
| `/ai/chat` و `/brain/chat` مساران | **نفس الـ Pipeline** — عبر HajeenBrainV3 |
| CORS مفتوح (`*`) | **Origins صريحة** — آمن |
| Brain Lazy Init | **Eager Init** — جاهز قبل أي طلب |

---

## استراتيجيات Multi-Model Collaboration

- **Chain** — كل نموذج يحسّن إجابة السابق
- **Ensemble** — جميع النماذج بالتوازي ثم دمج
- **Debate** — النماذج تتجادل للوصول لإجابة أفضل
- **Voting** — الإجابة الأكثر تشابهاً تفوز
- **Expert** — كل نموذج خبير في جانب محدد

---

## النقاط الدخول الموحّدة

كل هذه المسارات تمر بنفس الـ Pipeline عبر `HajeenBrainV3`:

| Endpoint | الوظيفة |
|----------|---------|
| `POST /ai/chat` | محادثة عبر Brain V3 |
| `POST /ai/chat/stream` | محادثة متدفقة عبر Brain V3 |
| `POST /brain/chat` | محادثة Brain مباشرة |
| `POST /brain/stream` | Brain متدفق |
| `WS /ws/chat` | WebSocket عبر Brain V3 |

---

*النسخة الموحّدة: V3.0.0 | آخر تحديث: 23 يوليو 2026*
