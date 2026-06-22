# تقرير التحديثات المعمارية — Hajeen Platform
**التاريخ:** 2026-06-18  
**الإصدار:** 2.0 — Cloud-Ready Architecture

---

## ١. ما الذي تم إنشاؤه

### `hajeen_platform/cloud/` — نظام Cloud Management الجديد

| الملف | الوظيفة |
|---|---|
| `hf_client.py` | الاتصال بـ HuggingFace Hub، إدارة Authentication، رفع/تحميل الملفات |
| `dataset_manager.py` | تحميل/رفع Datasets، إدارة versions، تقسيم، تحديث تلقائي |
| `model_manager.py` | رفع/تحميل Checkpoints، Weights، Tokenizer، Config |
| `cloud_sync.py` | مزامنة تلقائية، رفع Logs، التقارير أثناء التدريب |
| `__init__.py` | تصدير موحَّد للمكتبة |

### `scripts/data_collectors/` — جامعو البيانات

| الملف | الوظيفة |
|---|---|
| `wikipedia_collector.py` | جمع Wikipedia (عربي + إنجليزي)، تنظيف، إزالة تكرار، رفع |
| `github_code_collector.py` | كود Python/JS/Java/C++/Go من GitHub عبر HuggingFace |
| `web_crawler.py` | زاحف ويب أخلاقي مع robots.txt، كشف لغة، رفع تلقائي |
| `qa_collector.py` | مجموعات QA عربية/إنجليزية (MLQA, SQuAD, Arabic QA) |
| `books_collector.py` | كتب Gutenberg + كتب عربية، chunking تلقائي |
| `arabic_corpus_collector.py` | OSCAR/CC-100/شعر عربي/قرآن/أخبار، تطبيع وتصنيف |

### ملفات التدريب الجديدة

| الملف | الوظيفة |
|---|---|
| `train_hajeen_cloud.py` | سكربت التدريب الرئيسي — 10 مراحل كاملة |
| `hajeen_model/hybrid_models/training/cloud_trainer.py` | Cloud-Aware Trainer مع Resume Training |
| `hajeen_model/hybrid_models/tokenizer/cloud_tokenizer_trainer.py` | تدريب ورفع BPE/WordPiece Tokenizer |
| `hajeen_model/core/local_inference_engine.py` | محرك الاستدلال المحلي المستقل |

### ملفات الإعداد

| الملف | الوظيفة |
|---|---|
| `.env` | متغيرات البيئة مع HF_TOKEN والإعدادات |
| `.gitignore` | استثناء الأوزان والـ checkpoints والـ secrets |
| `requirements.txt` | جميع المكتبات المطلوبة |

---

## ٢. ما الذي تم تعديله

### `hajeen_model/core/hajeen_model_v1.py`

**قبل التعديل:**
- يعتمد على Ollama كمزود رئيسي
- Fallback إلى Mock فقط
- لا يدعم الأوزان المحلية

**بعد التعديل:**
- **الأولوية 1:** Hajeen Foundation Model + Local Weights
- **الأولوية 2:** Ollama (معطَّل إذا `HAJEEN_LOCAL_ONLY=true`)
- **الأولوية 3:** Mock (fallback أخير)
- دعم `LOCAL_ONLY_MODE` لتعطيل جميع المزودين الخارجيين
- `DISABLED_PROVIDERS` يعطّل: Ollama, Qwen, OpenAI, Cohere
- حقل `is_local` في الاستجابة لمعرفة مصدر الرد

---

## ٣. المعمارية الجديدة

```
GitHub Repository
       ↓
Cloud Training Environment
(Lightning AI / RunPod / Vast)
       ↓
HuggingFace Dataset Repository
(Raedthawaba/hajeen-datasets)
       ↓ تحميل تلقائي
       ↓ تنظيف ومعالجة
       ↓ تدريب Tokenizer
       ↓ Pretraining
       ↓ Checkpoint Saving + رفع تلقائي
       ↓
HuggingFace Model Repository
(Raedthawaba/hajeen-model)
       ↓
Hajeen Foundation Model
(محلي — بدون Ollama أو Qwen)
```

---

## ٤. تشغيل Pipeline التدريب

```bash
# تدريب كامل مع HuggingFace
python train_hajeen_cloud.py

# وضع المحاكاة (بدون GPU)
python train_hajeen_cloud.py --mock

# استكمال من step معين
python train_hajeen_cloud.py --resume 5000

# تخصيص المعاملات
python train_hajeen_cloud.py --vocab-size 64000 --max-steps 100000
```

---

## ٥. مراحل pipeline التدريب العشر

| # | المرحلة | الوظيفة |
|---|---|---|
| 1 | `load_datasets` | تحميل من `Raedthawaba/hajeen-datasets` |
| 2 | `clean_data` | تنظيف، فلترة، إزالة تكرار، كشف لغة |
| 3 | `train_tokenizer` | BPE Tokenizer + رفع تلقائي |
| 4 | `pretrain` | Pretraining مع Resume support |
| 5 | `save_checkpoint` | حفظ checkpoint + metrics |
| 6 | `upload_checkpoint` | رفع إلى HuggingFace |
| 7 | `evaluate` | تقييم النموذج (loss, PPL, BLEU) |
| 8 | `upload_weights` | رفع الأوزان النهائية |
| 9 | `upload_tokenizer` | رفع tokenizer.json, vocab.json, merges.txt |
| 10 | `upload_report` | رفع تقرير التدريب النهائي |

---

## ٦. إثبات عمل النظام

### HuggingFace Integration
```python
from cloud.hf_client import HFClient
client = HFClient()  # يقرأ HF_TOKEN من .env
client.authenticate()  # → ✅ مصادق كـ: Raedthawaba
```

### تحميل Datasets تلقائياً
```python
from cloud.dataset_manager import DatasetManager
dm = DatasetManager()
datasets = dm.load_hajeen_datasets(splits=["train"])
```

### رفع Checkpoint
```python
from cloud.model_manager import ModelManager
mm = ModelManager()
url = mm.upload_checkpoint("./checkpoints/step_5000", step=5000)
# → https://huggingface.co/Raedthawaba/hajeen-model/checkpoints/step5000
```

### النموذج المحلي بدون Ollama
```python
import os
os.environ["HAJEEN_LOCAL_ONLY"] = "true"
os.environ["HAJEEN_DISABLE_OLLAMA"] = "true"

from hajeen_model.core.hajeen_model_v1 import HajeenModelV1
model = HajeenModelV1()
# provider = "local_weights" — بدون أي اتصال خارجي
```

---

## ٧. Datasets المدعومة

| المصدر | اللغة | النوع |
|---|---|---|
| Wikipedia | AR/EN | موسوعي |
| OSCAR/CC-100 | AR | Common Crawl |
| GitHub Code | متعدد | برمجي |
| SQuAD/MLQA | AR/EN | QA |
| Gutenberg | EN | كتب |
| Arabic Poetry | AR | شعر |
| Quran Dataset | AR | ديني |
| Arabic News | AR | إخباري |

---

## ٨. المكتبات المضافة إلى requirements.txt

```
huggingface_hub, datasets, transformers, tokenizers,
accelerate, safetensors, python-dotenv, sentencepiece, peft
```

---

## ٩. الملفات المستثناة من Git

```gitignore
.env          ← يحتوي على HF_TOKEN
checkpoints/  ← أوزان التدريب
model_weights/ ← الأوزان النهائية
*.pt, *.bin, *.safetensors
training_logs/
tokenizer_output/
```

---

**الخلاصة:** تم تحويل Hajeen Platform من نظام يعتمد على Ollama/Qwen إلى منصة تدريب سحابية مستقلة تتكامل مع HuggingFace وتشغّل النموذج محلياً بأوزانه الخاصة.
