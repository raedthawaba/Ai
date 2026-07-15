# Changelog — Hajeen AI Platform

## [v2.0.0] — Hajeen Brain v2 — العقل المدبّر

### 🧠 إضافة Hajeen Brain v2 (الإضافة الكبرى)

أكبر تحديث في تاريخ المنصة — تحويل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

#### المكوّنات الجديدة:

**طبقة Hajeen Brain (`hajeen_platform/brain/`):**

| المكوّن | الوظيفة |
|---------|---------|
| `brain.py` | المنسّق الرئيسي — كل الطلبات تمر هنا |
| `goal_manager.py` | فهم الهدف الحقيقي للمستخدم (Intent + Complexity + Domain) |
| `task_decomposer.py` | تفكيك الأهداف إلى مهام مستقلة |
| `graph_planner.py` | بناء DAG للتنفيذ مع دعم التوازي |
| `decision_engine.py` | اختيار النموذج/الأداة بقواعد (بدون LLM) |
| `model_router.py` | توجيه ذكي مع Fallback تلقائي |
| `multi_model.py` | تعاون عدة نماذج (Chain/Ensemble/Debate/Voting/Expert) |
| `state_machine.py` | دورة حياة المهام (8 حالات) |

**الذاكرة (`brain/memory/`):**
- Session Memory، Conversation Memory، Long-Term Memory
- Semantic Memory، Episodic Memory، Procedural Memory، Agent Memory

**المعرفة (`brain/knowledge/`):**
- `knowledge_graph.py` — رسم بياني علائقي للمعرفة
- `knowledge_distillation.py` — استخلاص المعرفة من كل تفاعل مع نموذج خارجي

**التعلم (`brain/learning/`):**
- `continuous_learning.py` — خط تعلم كامل من 12 مرحلة مع Rollback

**التطوير الذاتي (`brain/reflection/`):**
- `self_reflection.py` — تقييم ذاتي بعد كل تنفيذ
- `self_evolution.py` — تطوير قواعد النظام ذاتياً

**السياسات (`brain/policy/`):**
- `policy_engine.py` — 5 سياسات: أمان، خصوصية، ميزانية، أخلاقيات، Local-First

**القياس (`brain/metrics/`):**
- `model_performance_db.py` — قاعدة بيانات شاملة لأداء كل نموذج

**السيادة (`brain/sovereignty/`):**
- `sovereignty_layer.py` — قياس الاستقلالية عن النماذج الخارجية

**التحسين (`brain/improvement/`):**
- `autonomous_improvement.py` — تحليل أسبوعي وتحسين ذاتي

#### API Endpoints الجديدة:
- `POST /api/v1/brain/chat` — المحادثة الكاملة عبر Brain
- `POST /api/v1/brain/stream` — Streaming عبر Brain
- `POST /api/v1/brain/analyze` — تحليل الطلب فقط
- `GET /api/v1/brain/status` — حالة شاملة
- `GET /api/v1/brain/sovereignty` — تقرير الاستقلالية
- `GET /api/v1/brain/knowledge/{entity}` — السياق المعرفي
- `POST /api/v1/brain/weekly-analysis` — التحليل الأسبوعي
- `GET /api/v1/brain/performance` — أداء النماذج
- `GET /api/v1/brain/decisions` — قرارات Decision Engine
- `GET /api/v1/brain/reflections` — تقارير Self Reflection
- `GET /api/v1/brain/evolution` — اقتراحات Self Evolution
- `GET /api/v1/brain/distillation` — إحصائيات Distillation
- `POST /api/v1/brain/learn` — إضافة بيانات تدريب
- `GET /api/v1/brain/memory/{session_id}` — ذاكرة الجلسة

---

## [v1.1.0] — Phase 10 — Production Stable

- Pipeline Orchestration
- Distributed Storage
- Multi-Tenant Architecture
- Security & Auth Middleware
- AI Inference Engine
- CI/CD Support

## [v1.0.0] — Phase 1-9

- Data ingestion (RSS, Web, Social)
- Vector Search (FAISS)
- RAG Pipeline
- LLM Providers (Ollama, OpenAI, HuggingFace, Mistral)
- Memory Management
- Training Pipeline (DPO, PPO, RLHF)
- Distributed Processing (Celery, Ray)
- Monitoring (Prometheus, Grafana)
