# Hajeen AI — Workflows Documentation
## توثيق سير العمل

---

## تشغيل النظام

### 1. تثبيت المتطلبات
```bash
cd hajeen_platform
pip install -r requirements.txt
```

### 2. تشغيل Redis (مطلوب للـ Celery Workers)
```bash
docker-compose up -d redis
```

### 3. تشغيل API Server
```bash
uvicorn hajeen_platform.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. تشغيل Celery Workers
```bash
# CPU Worker
celery -A hajeen_platform.workers.celery_app worker --queues=cpu_queue --concurrency=4

# GPU Worker (إذا توفر GPU)
celery -A hajeen_platform.workers.celery_app worker --queues=gpu_queue --concurrency=1
```

### 5. تشغيل Monitoring
```bash
docker-compose up -d prometheus grafana
```

### 6. تشغيل الكل دفعة واحدة
```bash
docker-compose up -d
```

---

## سير عمل التطوير

### إضافة Endpoint جديد
1. تعريف Schema في `api/v1/ai/models.py`
2. إضافة Route في `api/v1/ai/router.py`
3. تنفيذ الـ Handler في الـ view function
4. ربط بـ Brain أو الخدمة المناسبة
5. كتابة اختبار في `tests/integration/`

### إضافة نموذج جديد
1. إضافة إعدادات النموذج في `brain/model_router_v3.py`
2. إضافة معرف في القائمة المعروفة بـ `decision_engine_v3.py`
3. اختبار الـ routing في `tests/unit/`

### تشغيل pipeline التعلم
```python
from hajeen_platform.brain.learning.continuous_learning import get_learning_pipeline

pipeline = get_learning_pipeline()

# جمع البيانات
raw_data = [
    {"instruction": "...", "output": "...", "quality_score": 0.85}
    for _ in range(100)
]

# تشغيل الـ pipeline
run = await pipeline.run(raw_data)
print(f"Status: {run.status}")
print(f"Evaluation: {run.evaluation_results}")
```

---

## سير عمل الاختبارات

### تشغيل Unit Tests
```bash
cd hajeen_platform
pytest tests/unit/ -v --tb=short
```

### تشغيل Integration Tests
```bash
pytest tests/integration/ -v --tb=short
```

### تشغيل Load Tests
```bash
pytest tests/load/ -v -s --tb=short
```

### تشغيل Stress Tests
```bash
pytest tests/stress/ -v --tb=short
```

### تشغيل Benchmark Tests
```bash
pytest tests/benchmark/ -v -s --tb=short
```

### تشغيل كل الاختبارات
```bash
pytest tests/ -v --tb=short --ignore=tests/load --ignore=tests/stress
```

### قياس التغطية
```bash
pytest tests/unit/ tests/integration/ --cov=hajeen_platform --cov-report=html
```

---

## سير عمل النشر (Deployment)

### 1. بناء Docker Image
```bash
docker build -t hajeen-ai:latest .
```

### 2. فحص الصحة
```bash
curl http://localhost:8000/api/v1/health
```

### 3. نشر الـ Nginx (Load Balancer)
```bash
docker-compose -f docker-compose.prod.yml up -d nginx
```

### 4. Horizontal Scaling
```bash
# تشغيل 3 نسخ من API
docker-compose scale api=3
```

---

## سير عمل المراقبة

### فحص صحة النظام
```bash
curl http://localhost:8000/api/v1/health | jq
```

### عرض Logs
```bash
# API logs
docker-compose logs -f api

# Worker logs
docker-compose logs -f worker-cpu

# Brain logs
tail -f logs/brain.log
```

### مراقبة الأداء (Prometheus)
```
http://localhost:9090
```

### Grafana Dashboard
```
http://localhost:3000
الرمز الافتراضي: admin/hajeen_grafana
```

### الاستعلام عن إحصائيات النظام
```bash
curl http://localhost:8000/api/v1/brain/stats | jq
curl http://localhost:8000/api/v1/learning/stats | jq
curl http://localhost:8000/api/v1/sovereignty/report | jq
```

---

## سير عمل Rollback

### Rollback النموذج
```python
from hajeen_platform.brain.learning.continuous_learning import get_learning_pipeline
import json

# فحص سجل النماذج
with open("storage_data/brain/learning/model_registry.json") as f:
    registry = json.load(f)

# اختيار الإصدار السابق
previous_version = registry["models"][-2]["model_version"]

# تحديث النموذج النشط
with open("storage_data/brain/learning/active_model.json", "w") as f:
    json.dump({"version": previous_version, "updated_at": time.time()}, f)
```

### Rollback كامل للنظام
```bash
# التراجع للـ checkpoint السابق
git checkout <commit_hash>
docker-compose down && docker-compose up -d
```

---

## سير عمل استكشاف الأخطاء

### فحص حالة الـ Pipeline
```python
pipeline = get_learning_pipeline()
stats = pipeline.get_stats()
print(stats)

# فحص run محدد
run = pipeline.get_run("run_id_here")
print(run.stage_history)  # تاريخ كل مرحلة
print(run.error)          # سبب الفشل إن وُجد
```

### فحص جودة النموذج
```python
from hajeen_platform.brain.decision_engine_v3 import get_decision_engine_v3

engine = get_decision_engine_v3()
quality = await engine._get_model_quality("your-model-id")
print(f"Quality: {quality}")
```

### فحص الذاكرة
```python
memory = get_memory_fabric()
lt = memory.get_long_term_memory("session_id")
keys = lt.list_keys()
for key in keys[:5]:
    entry = lt.recall(key)
    print(f"{key}: {entry}")
```
