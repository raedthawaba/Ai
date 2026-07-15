# Hajeen Brain v2 — العقل المدبّر لمنصة Hajeen AI

## المفهوم

**Hajeen Brain** هو أعلى طبقة في منصة Hajeen AI.  
لا يصل أي طلب مباشرةً إلى أي نموذج لغوي — كل الطلبات تمر عبر Hajeen Brain أولاً.

```
المستخدم
    ↓
Hajeen Brain ← الطبقة العليا
    ↓
Policy Engine ← أمان + أخلاقيات + ميزانية
    ↓
Goal Manager ← فهم الهدف الحقيقي
    ↓
Task Decomposer ← تفكيك إلى مهام صغيرة
    ↓
Graph Planner ← DAG قابل للتوازي
    ↓
Decision Engine ← اختيار النموذج/الأداة
    ↓
Model Router / Multi-Model ← التنفيذ
    ↓
Knowledge Distillation ← استخلاص المعرفة
    ↓
Memory Fabric ← حفظ السياق
    ↓
Self Reflection ← تقييم ذاتي
    ↓
Sovereignty Layer ← تسجيل الاستقلالية
```

---

## المبدأ الذهبي

> أي نموذج خارجي = **Temporary Expert** فقط.  
> كل معرفة تُكتسب من الخارج تتحول تدريجياً إلى معرفة داخلية يمتلكها Hajeen.

---

## المكوّنات

| المكوّن | الملف | الوظيفة |
|---------|-------|---------|
| **HajeenBrain** | `brain.py` | المنسّق الرئيسي — المسار الكامل |
| **Goal Manager** | `goal_manager.py` | فهم الهدف الحقيقي للمستخدم |
| **Task Decomposer** | `task_decomposer.py` | تفكيك الأهداف إلى مهام مستقلة |
| **Graph Planner** | `graph_planner.py` | بناء DAG قابل للتوازي |
| **Decision Engine** | `decision_engine.py` | اختيار النموذج/الأداة بقواعد |
| **Model Router** | `model_router.py` | توجيه ذكي مع Fallback |
| **Multi-Model** | `multi_model.py` | تعاون عدة نماذج (Chain/Ensemble/Debate) |
| **State Machine** | `state_machine.py` | دورة حياة المهام |
| **Memory Fabric** | `memory/memory_fabric.py` | 7 أنواع ذاكرة موحّدة |
| **Knowledge Graph** | `knowledge/knowledge_graph.py` | الرسم البياني للمعرفة |
| **Knowledge Distillation** | `knowledge/knowledge_distillation.py` | استخلاص المعرفة من النماذج |
| **Continuous Learning** | `learning/continuous_learning.py` | خط التعلم المستمر |
| **Self Reflection** | `reflection/self_reflection.py` | تقييم ذاتي بعد كل تنفيذ |
| **Self Evolution** | `reflection/self_evolution.py` | تطوير قواعد النظام ذاتياً |
| **Policy Engine** | `policy/policy_engine.py` | سياسات الأمان والأخلاقيات |
| **Model Performance DB** | `metrics/model_performance_db.py` | قاعدة بيانات أداء النماذج |
| **Sovereignty Layer** | `sovereignty/sovereignty_layer.py` | قياس الاستقلالية عن النماذج الخارجية |
| **Autonomous Improvement** | `improvement/autonomous_improvement.py` | تحليل أسبوعي وتحسين ذاتي |

---

## API Endpoints

| Method | Path | الوظيفة |
|--------|------|---------|
| POST | `/api/v1/brain/chat` | محادثة كاملة عبر Brain |
| POST | `/api/v1/brain/stream` | محادثة متدفقة (SSE) |
| POST | `/api/v1/brain/analyze` | تحليل طلب بدون تنفيذ |
| GET | `/api/v1/brain/status` | حالة شاملة للـ Brain |
| GET | `/api/v1/brain/sovereignty` | تقرير الاستقلالية |
| GET | `/api/v1/brain/knowledge/{entity}` | السياق المعرفي |
| POST | `/api/v1/brain/weekly-analysis` | التحليل الأسبوعي |
| GET | `/api/v1/brain/performance` | أداء النماذج |
| GET | `/api/v1/brain/decisions` | قرارات Decision Engine |
| GET | `/api/v1/brain/reflections` | تقارير Self Reflection |
| GET | `/api/v1/brain/evolution` | اقتراحات Self Evolution |
| GET | `/api/v1/brain/distillation` | إحصائيات Distillation |
| POST | `/api/v1/brain/learn` | إضافة بيانات تدريب |
| GET | `/api/v1/brain/memory/{session_id}` | ذاكرة الجلسة |

---

## أنواع ذاكرة Memory Fabric

1. **Session Memory** — ذاكرة الجلسة (تُمسح عند الانتهاء)
2. **Conversation Memory** — سجل المحادثات (نافذة منزلقة)
3. **Long-Term Memory** — ذاكرة دائمة (JSON)
4. **Semantic Memory** — ذاكرة دلالية (بحث بالمعنى)
5. **Episodic Memory** — ذاكرة الأحداث المهمة
6. **Procedural Memory** — ذاكرة كيفية تنفيذ المهام
7. **Agent Memory** — ذاكرة خاصة بكل وكيل

---

## أهداف الاستقلالية

| السنة | الهدف |
|-------|-------|
| Year 1 | 30% محلي |
| Year 2 | 50% محلي |
| Year 3 | 70% محلي |
| Year 5 | 90% محلي (Fully Sovereign) |

---

## مراحل Continuous Learning Pipeline

```
Collection → Cleaning → Deduplication → Quality Validation
→ Filtering → Ranking → Human Approval (Optional)
→ Dataset Builder → Training Queue → Fine-Tuning
→ Evaluation → Deployment → Rollback
```

---

## استراتيجيات Multi-Model Collaboration

- **Chain** — كل نموذج يحسّن إجابة السابق
- **Ensemble** — جميع النماذج بالتوازي ثم دمج
- **Debate** — النماذج تتجادل للوصول لإجابة أفضل
- **Voting** — الإجابة الأكثر تشابهاً تفوز
- **Expert** — كل نموذج خبير في جانب محدد
