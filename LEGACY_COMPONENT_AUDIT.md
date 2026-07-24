# LEGACY_COMPONENT_AUDIT.md
## تقرير مراجعة المكونات القديمة — Hajeen AI Platform

**تاريخ المراجعة:** 2026-07-24  
**الإصدار:** Architecture Consolidation v1.0  
**المرحلة:** Architecture Freeze Pre-Validation

---

## ملخص تنفيذي

تم مراجعة جميع مكونات المنصة وتصنيفها إلى ثلاث فئات:
- **Active Component** — مكون نشط يحتوي منطق تشغيل حقيقي
- **Compatibility Shim** — يسمح للكود القديم بالعمل عبر توجيه للمكونات الحديثة
- **Dead Code** — لا يوجد له استعمال ويمكن حذفه

---

## Brain Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `brain/brain_v3.py` | **Active** | إبقاء — العقل المركزي الوحيد | HajeenBrainV3 v3.0.0 |
| `brain/__init__.py` | **Active** | إبقاء — exports موحّدة | يصدّر get_brain, get_brain_v3, HajeenBrainV3 |
| `brain/api/brain_router.py` | **Active** | إبقاء — محوّل من v2 لـ v3 adapter | يستخدم get_brain_v3 حصراً |
| `brain/model_router.py` | **Active** | إبقاء — الموجه الوحيد للنماذج | ModelRouter Singleton |
| `brain/decision_engine.py` | **Active** | إبقاء — طبقة القرار | يُستخدم داخل Brain Pipeline |
| `brain/policy/policy_engine.py` | **Active** | إبقاء — طبقة السياسات | |
| `brain/memory/memory_fabric.py` | **Active** | إبقاء — مصدر الحقيقة الوحيد | MemoryFabric SSOT |
| `brain/memory/unified_interface.py` | **Active** | إبقاء — جسر الذاكرة الموحّد | UnifiedMemoryInterface |
| `brain/cognitive_layer/*.py` | **Active** | إبقاء — طبقات التحليل الإدراكي | 15+ مكوّن |
| `brain/reflection/self_reflection.py` | **Active** | إبقاء | |
| `brain/reflection/self_evolution.py` | **Active** | إبقاء | |
| `brain/knowledge/knowledge_graph.py` | **Active** | إبقاء | |
| `brain/knowledge/knowledge_distillation.py` | **Active** | إبقاء | |
| `brain/sovereignty/sovereignty_layer.py` | **Active** | إبقاء | |
| `brain/multi_model.py` | **Active** | إبقاء | |
| `brain/prompts/unified_prompt_builder.py` | **Active** | **جديد** — UnifiedPromptBuilder | نقطة الدخول الوحيدة للـ Prompts |

---

## Memory Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `brain/memory/memory_fabric.py` | **Active** | إبقاء — SSOT | مصدر الحقيقة الوحيد |
| `brain/memory/unified_interface.py` | **Active** | إبقاء — Bridge | توجيه لـ MemoryFabric |
| `services/memory/session_manager.py` | **Shim** | إبقاء كـ Adapter | يوجّه لـ UnifiedMemoryInterface → MemoryFabric |
| `services/memory/conversation_memory.py` | **Shim** | إبقاء كـ Adapter | يوجّه لـ UnifiedMemoryInterface → MemoryFabric |
| `core/memory/memory_manager.py` | **Shim** | إبقاء كـ Adapter | يوجّه لـ UnifiedMemoryInterface → MemoryFabric |
| `services/memory/summarization_memory.py` | **Shim** | مراجعة | قد يحتاج تحويل |
| `services/memory_service.py` | **Shim** | مراجعة | قد يحتاج تحويل |

---

## Prompt Builder Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `brain/prompts/unified_prompt_builder.py` | **Active** | **جديد** — المصدر الوحيد | UnifiedPromptBuilder |
| `core/prompts/base.py` | **Active** | إبقاء — AbstractPromptBuilder | الواجهة المجردة الأساسية |
| `core/prompts/prompt_builder.py` | **Shim** | إبقاء | يرث AbstractPromptBuilder، يُحوّل تدريجياً لـ UnifiedPromptBuilder |
| `services/prompts/prompt_builder.py` | **Shim** | إبقاء | يرث AbstractPromptBuilder |
| `services/rag/prompt_builder.py` | **Shim** | إبقاء | يرث AbstractPromptBuilder، يُوجَّه عبر UnifiedPromptBuilder |

---

## Model Router Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `brain/model_router.py` | **Active** | إبقاء — الموجه الوحيد | ModelRouter Singleton |
| `api/v1/hajeen_model_router.py` | **Active** | محوّل لـ HTTP Adapter | يوجّه جميع الطلبات لـ HajeenBrainV3 |
| `brain/api/brain_router.py` | **Active** | محوّل من v2 لـ v3 | لا يحتوي منطق AI مستقل |

---

## API Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `api/main.py` | **Active** | إبقاء | FastAPI Application |
| `api/v1/ai/chat.py` | **Active** | **محوّل** — إزالة الـ Fallback | جميع الطلبات عبر HajeenBrainV3 |
| `api/v1/ai/completion.py` | **Active** | مراجعة مطلوبة | قد يحتوي على LLM مباشر |
| `api/v1/ai/router.py` | **Active** | إبقاء | |
| `api/v1/router.py` | **Active** | إبقاء | |

---

## Services Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `services/chat/chat_service.py` | **Shim** | إبقاء كـ Adapter | يوجّه لـ HajeenBrainV3 |
| `services/chat/chat_session.py` | **Shim** | إبقاء | متوافق مع chat_service |
| `services/rag/rag_pipeline.py` | **Active** | إبقاء | RAG pipeline |
| `services/rag_service.py` | **Active** | مراجعة | |
| `services/inference_service.py` | **Shim** | مراجعة | قد يستدعي LLM مباشرةً |
| `services/agent_service.py` | **Active** | مراجعة | |

---

## Core Layer

| الملف | الحالة | القرار | الملاحظة |
|-------|--------|---------|----------|
| `core/inference_engine/` | **Shim** | إبقاء للتوافقية | يجب ألا يُستدعى مباشرةً من API |
| `core/prompts/base.py` | **Active** | إبقاء — AbstractPromptBuilder | |
| `core/prompts/prompt_builder.py` | **Shim** | إبقاء | سيُوجَّه لـ UnifiedPromptBuilder |
| `core/llm/` | **Active** | إبقاء | يُستخدم بواسطة ModelRouter فقط |

---

## اتخاذ القرارات

### مبدأ الإبقاء
لا يتم حذف أي مكون إلا بعد التأكد من:
1. عدم وجود أي استدعاء له في أي مكان
2. عدم تأثيره على أي اختبار موجود
3. الحصول على موافقة صريحة

### مبدأ التحويل
كل مكون قديم يُحوَّل لـ Adapter يوجّه للمكونات الجديدة:
```
Old Component → Compatibility Layer → UnifiedInterface → SSOT Component
```

### مبدأ المنع
يُمنع تماماً:
- أي LLM call خارج `brain/model_router.py`
- أي كتابة في الذاكرة خارج `brain/memory/memory_fabric.py`
- أي بناء Prompt خارج `brain/prompts/unified_prompt_builder.py`

---

## إجراءات المرحلة التالية

1. **مراجعة** `services/inference_service.py` للتأكد من عدم وجود LLM مباشر
2. **مراجعة** `api/v1/ai/completion.py` للتأكد من المرور عبر Brain
3. **مراجعة** `api/v1/ai/websocket.py` للتأكد من التوحيد
4. **إضافة** اختبارات تكاملية شاملة
5. **توثيق** المعمارية النهائية في ARCHITECTURE_FREEZE_REPORT.md

---

*تم إنشاء هذا التقرير كجزء من Architecture Consolidation Phase — Hajeen AI Platform*
