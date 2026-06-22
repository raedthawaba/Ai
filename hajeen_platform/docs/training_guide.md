# Hajeen Model v1 — دليل التدريب

## نظرة عامة

يستخدم Hajeen Model v1 تقنية **LoRA (Low-Rank Adaptation)** للـ Fine-Tuning الفعّال على نموذج Qwen2.5-1.5B.

## اختيار النموذج الأساسي

بعد دراسة الخيارات المتاحة، تم اختيار **Qwen2.5-1.5B** لهذه الأسباب:

| المعيار | Qwen2.5-1.5B | LLaMA 3.2 | Mistral 7B | Phi-3 | Gemma 2B |
|---|---|---|---|---|---|
| دعم العربية | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| حجم النموذج | 1.5B ✅ | 3B | 7B | 3.8B | 2B |
| متطلبات GPU | 4GB | 6GB | 14GB | 8GB | 5GB |
| جودة النتائج | ممتازة | جيدة | ممتازة | جيدة | جيدة |
| Ollama متاح | ✅ | ✅ | ✅ | ✅ | ✅ |

**الخلاصة**: Qwen2.5-1.5B هو الأنسب لمنصة حجين بسبب دعمه الممتاز للغة العربية وصغر حجمه.

## الخطوات التفصيلية

### الخطوة 1: جمع البيانات

```bash
# تشغيل demo pipeline لجمع بيانات تجريبية
./run.sh demo

# إضافة قنوات RSS جديدة
python -m data_engine.cli create-channel \
    --name "BBC Arabic" \
    --type rss \
    --url "https://feeds.bbci.co.uk/arabic/rss.xml"

# تفعيل وجمع البيانات
python -m data_engine.cli trigger CHANNEL_ID

# توسيع المصادر تلقائياً
python scripts/data/expand_sources.py --add-all
```

### الخطوة 2: تحليل البيانات

```bash
python scripts/data/expand_sources.py --analyze
```

النتيجة المتوقعة:
```
إجمالي السجلات: 31 (حالياً — غير كافٍ)
يحتاج: 969 سجل إضافي على الأقل (للحد الأدنى 1000)
للتدريب الجيد: 10,000+ سجل
```

### الخطوة 3: بناء Dataset

```bash
# عبر سكريبت التدريب
python scripts/training/run_training.py --build-dataset-only --synthetic 500

# أو عبر API
curl -X POST http://localhost:8000/api/v1/model/training/build-dataset \
     -H "Content-Type: application/json" \
     -d '{"add_synthetic": 500}'
```

**ملف الإخراج**:
- `hajeen_model/data/dataset_train.jsonl`
- `hajeen_model/data/dataset_eval.jsonl`

**تنسيق Alpaca**:
```json
{
  "instruction": "لخّص المقالة التالية:",
  "input": "العنوان: ...\n\nالمحتوى: ...",
  "output": "ملخص المقالة..."
}
```

### الخطوة 4: محاكاة التدريب (بدون GPU)

```bash
python scripts/training/run_training.py --simulate
```

### الخطوة 5: التدريب الفعلي (على GPU خارجي)

**متطلبات**:
- GPU بذاكرة 8GB+ (RTX 3090 أو A100 أو T4)
- CUDA 11.8+
- Python 3.10+

```bash
# تثبيت المكتبات
pip install torch transformers peft trl accelerate datasets wandb

# تدريب
python scripts/training/run_training.py \
    --base-model Qwen/Qwen2.5-1.5B \
    --epochs 3 \
    --batch-size 4 \
    --lr 2e-4
```

**على Google Colab (مجاناً)**:
```python
# في Colab
!git clone <your-repo>
%cd hajeen_platform
!pip install -r requirements/gpu.txt
!python scripts/training/run_training.py --base-model Qwen/Qwen2.5-1.5B --epochs 3
```

### الخطوة 6: تصدير النموذج إلى Ollama

```bash
# بعد التدريب، تحويل النموذج إلى GGUF
pip install llama.cpp
python -m llama_cpp.convert \
    --model hajeen_model/checkpoints/final \
    --outfile hajeen_model/hajeen_v1.gguf \
    --type q4_k_m

# إنشاء Modelfile
cat > Modelfile << 'EOF'
FROM ./hajeen_model/hajeen_v1.gguf
SYSTEM """أنت Hajeen Model v1، مساعد ذكي متخصص في تحليل الأخبار العربية."""
PARAMETER temperature 0.7
PARAMETER num_ctx 4096
EOF

# تسجيل في Ollama
ollama create hajeen-v1 -f Modelfile

# تشغيل
ollama run hajeen-v1 "مرحبا، كيف يمكنك مساعدتي؟"
```

## مراقبة التدريب

```bash
# متابعة السجلات
tail -f hajeen_model/logs/exp_*/metrics*.jsonl

# عرض Checkpoints
curl http://localhost:8000/api/v1/model/training/checkpoints
```

## حسابات الموارد

| الإعداد | GPU | RAM | وقت/Epoch (1K مثال) |
|---|---|---|---|
| RTX 3090 (24GB) | نعم | 32GB | ~10 دقيقة |
| RTX 3080 (10GB) | نعم | 16GB | ~20 دقيقة |
| T4 (Colab) | نعم | 12GB | ~30 دقيقة |
| CPU فقط | لا | 8GB | ساعات (غير عملي) |
