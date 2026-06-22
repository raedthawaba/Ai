# Hajeen AI Platform — وثائق البنية المعمارية

## نظرة عامة

منصة حجين هي منصة ذكاء اصطناعي متكاملة تجمع بين جمع البيانات والمعالجة والبحث الدلالي والاستدلال بالنموذج المحلي.

```
┌─────────────────────────────────────────────────────────────┐
│                    Hajeen AI Platform                       │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Data     │  │ Vector   │  │   RAG    │  │  Hajeen   │  │
│  │ Engine   │→ │ Store    │→ │ System   │→ │ Model v1  │  │
│  │ (RSS)    │  │ (FAISS)  │  │          │  │ (Ollama)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│       ↓              ↓             ↓              ↓         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              FastAPI REST + WebSocket               │   │
│  └─────────────────────────────────────────────────────┘   │
│       ↓              ↓             ↓                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  Agent   │  │ Training │  │Monitoring│                  │
│  │  System  │  │ Pipeline │  │          │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## المكونات الرئيسية

### 1. Data Engine (محرك البيانات)
- **المسار**: `data_engine/`
- **الوظيفة**: جمع ومعالجة الأخبار من مصادر RSS
- **المكونات**:
  - `channels/` — إدارة قنوات البيانات
  - `ingestion/` — استقبال البيانات
  - `processing/` — معالجة وتنظيف البيانات
  - `pipelines/` — خطوط المعالجة
  - `storage/` — طبقات التخزين (Bronze → Silver → Gold)

### 2. Embedding Engine (محرك التضمين)
- **المسار**: `core/embeddings/`
- **النموذج**: sentence-transformers
- **الوظيفة**: تحويل النصوص إلى متجهات للبحث الدلالي

### 3. Vector Store (مخزن المتجهات)
- **المحرك**: FAISS (محلي)
- **الوظيفة**: بحث دلالي سريع وفعال
- **الحفظ**: `storage_data/vector_index/`

### 4. RAG System (نظام الاسترجاع)
- **المسار**: `services/rag/`
- **المكونات**:
  - `retriever.py` — استرجاع المستندات
  - `reranker.py` — إعادة ترتيب النتائج
  - `context_builder.py` — بناء السياق
  - `hybrid_search.py` — بحث هجين

### 5. Hajeen Model v1 (النموذج المحلي)
- **المسار**: `hajeen_model/`
- **المحرك**: Ollama (تشغيل محلي)
- **النموذج الأساسي**: Qwen2.5-1.5B
- **الـ Fallback**: Mock Provider (للتطوير)
- **المكونات**:
  - `hajeen_model_v1.py` — الواجهة الرئيسية
  - `ollama_manager.py` — إدارة Ollama
  - `dataset_builder.py` — بناء بيانات التدريب
  - `training_pipeline.py` — منظومة التدريب

### 6. LLM Manager (مدير النماذج)
- **المسار**: `core/llm/`
- **المزودون**:
  - `ollama` — النموذج المحلي (الرئيسي)
  - `huggingface` — HuggingFace Hub
  - `mock` — للاختبار والتطوير
- **نظام Fallback**: تلقائي عند تعذر الاتصال

### 7. Inference Engine (محرك الاستدلال)
- **المسار**: `core/inference_engine/`
- **الميزات**:
  - طلبات متزامنة وغير متزامنة
  - Streaming
  - Queue management
  - Token tracking

### 8. Agent System (نظام الوكلاء)
- **المسار**: `services/agents/`
- **الوكلاء**:
  - `planner_agent.py` — تخطيط المهام
  - `execution_agent.py` — تنفيذ المهام
  - `retrieval_agent.py` — استرجاع المعلومات
  - `memory_agent.py` — إدارة الذاكرة
  - `tool_agent.py` — استخدام الأدوات

### 9. Training Pipeline (منظومة التدريب)
- **المسار**: `hajeen_model/training_pipeline.py`
- **المكونات**:
  - Dataset Builder — بناء بيانات التدريب
  - LoRA Trainer — Fine-Tuning بكفاءة
  - Checkpoint Manager — إدارة نقاط الحفظ
  - Metrics Logger — تسجيل المقاييس
  - Model Evaluator — تقييم النموذج

### 10. API Layer (طبقة API)
- **المسار**: `api/`
- **الإطار**: FastAPI
- **المسارات**:
  - `/api/v1/channels` — إدارة قنوات البيانات
  - `/api/v1/search` — البحث الدلالي
  - `/api/v1/embeddings` — التضمين
  - `/api/v1/ai/*` — استدلال AI
  - `/api/v1/model/*` — Hajeen Model v1
  - `/ws/chat` — WebSocket Chat

## تدفق البيانات

```
RSS Sources → Data Engine → Processing Pipeline → Vector Store
                                                        ↓
User Query → API → RAG System (Retrieve + Rerank) → Hajeen Model v1
                                                        ↓
                                               Generated Response
```

## قرارات معمارية

1. **Ollama بدلاً من API خارجية**: تشغيل محلي كامل بدون اعتماد على الإنترنت
2. **FAISS محلياً**: لا قواعد بيانات خارجية للمتجهات
3. **LoRA Fine-Tuning**: تدريب فعال بذاكرة GPU أقل
4. **Mock Provider**: للتطوير والاختبار بدون نموذج فعلي
5. **Celery In-Memory**: لا يحتاج Redis في بيئة التطوير
6. **Layered Storage**: Bronze → Silver → Gold لجودة بيانات تدريجية

## متطلبات التشغيل

| المكون | الحد الأدنى | الموصى به |
|---|---|---|
| RAM | 4GB | 16GB+ |
| القرص | 10GB | 100GB+ |
| GPU (التدريب) | 8GB VRAM | 24GB+ VRAM |
| GPU (الاستدلال) | اختياري | 4GB VRAM |
