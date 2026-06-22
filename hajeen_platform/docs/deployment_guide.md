# دليل النشر والتشغيل — Hajeen AI Platform

## التشغيل السريع

```bash
cd hajeen_platform

# 1. تثبيت المتطلبات
pip install fastapi uvicorn pydantic httpx pyyaml feedparser beautifulsoup4

# 2. إعداد Ollama (اختياري — للنموذج الحقيقي)
bash scripts/deployment/setup_ollama.sh

# 3. تشغيل المنصة
./run.sh api
# أو
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# 4. فتح الوثائق
open http://localhost:8000/docs
```

## متغيرات البيئة

انسخ `.env.example` إلى `.env`:

```bash
cp .env.example .env
```

### الإعدادات الرئيسية

```env
# تشغيل محلي بدون Redis
CELERY_USE_MEMORY=1

# تفعيل Ollama
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:1.5b
OLLAMA_BASE_URL=http://localhost:11434

# للاختبار بدون Ollama
LLM_PROVIDER=mock
```

## مسارات API الرئيسية

| المسار | الوظيفة |
|---|---|
| `GET /health` | فحص صحة المنصة |
| `GET /docs` | وثائق Swagger |
| `POST /api/v1/model/chat` | محادثة مع النموذج |
| `GET /api/v1/model/health` | حالة Hajeen Model v1 |
| `GET /api/v1/model/ollama/status` | حالة Ollama |
| `POST /api/v1/model/training/build-dataset` | بناء بيانات التدريب |
| `POST /api/v1/model/training/simulate` | محاكاة التدريب |
| `POST /api/v1/model/evaluate` | تقييم النموذج |
| `POST /api/v1/channels/` | إضافة قناة RSS |
| `GET /api/v1/search/` | البحث الدلالي |

## تدفق التشغيل الكامل

```
1. ./run.sh api                  → تشغيل FastAPI
2. ./run.sh demo                 → جمع بيانات تجريبية
3. ollama serve                  → تشغيل Ollama
4. ollama pull qwen2.5:1.5b      → تحميل النموذج
5. curl /api/v1/model/health     → التحقق
6. curl /api/v1/model/chat       → اختبار المحادثة
```

## إعادة التدريب (Hajeen Model v2)

```bash
# جمع المزيد من البيانات أولاً
python scripts/data/expand_sources.py --add-all
./run.sh worker &
./run.sh trigger CHANNEL_ID

# إعادة التدريب
bash scripts/deployment/retrain_v2.sh Qwen/Qwen2.5-1.5B 3 v2

# أو يدوياً
python scripts/training/run_training.py \
    --base-model Qwen/Qwen2.5-3B \  # نموذج أكبر
    --epochs 5 \
    --synthetic 0
```
