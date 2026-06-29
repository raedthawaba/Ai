# المرحلة الثامنة: تطوير Data Intelligence Layer (Autonomous Data Factory)

تهدف هذه المرحلة إلى تحويل عملية إدارة البيانات في Hajeen AI Platform إلى نظام ذاتي التشغيل وذكي، قادر على توليد البيانات، تحسينها، ودمجها بشكل مستقل. هذا يضمن توفر بيانات عالية الجودة ومحدثة باستمرار لدعم نماذج الذكاء الاصطناعي.

## المكونات الرئيسية المضافة:

### 1. Autonomous Data Factory (`data_factory.py`)
- **الوظيفة:** المحرك المركزي الذي يدير دورة حياة البيانات بشكل مستقل، من التوليد إلى التحسين والدمج.
- **القدرات:**
    - تسجيل مولدات البيانات (Data Generators) لإنشاء بيانات اصطناعية أو جمعها من مصادر مختلفة.
    - تسجيل أدوات تحسين البيانات (Data Refiners) لتنظيف، إثراء، أو تحويل مجموعات البيانات.
    - تسجيل مسارات دمج البيانات (Ingestion Pipelines) لإدخال البيانات المحسنة إلى أنظمة التخزين (مثل قواعد البيانات المتجهة).
    - تشغيل حلقة ذاتية التشغيل (Autonomous Loop) لتوليد البيانات وتحسينها ودمجها بشكل مستمر.

### 2. Data Intelligence Components (`components.py`)
- **الوظيفة:** توفير أمثلة لمكونات ذكاء البيانات التي يمكن استخدامها مع Autonomous Data Factory.
- **المكونات المطبقة حاليًا (أمثلة):**
    - `synthetic_data_generator`: لتوليد بيانات اصطناعية بناءً على مخطط محدد باستخدام LLM.
    - `dataset_refiner`: لتحسين مجموعة بيانات موجودة بناءً على قواعد محددة باستخدام LLM.
    - `vector_store_ingestion_pipeline`: لمحاكاة عملية دمج البيانات في متجر متجه (Vector Store).
    - `MockLLM` و `MockVectorDBClient`: لتمكين الاختبارات دون الحاجة إلى نماذج LLM أو قواعد بيانات متجهة حقيقية.

## التكامل والتشغيل:

تم تصميم Autonomous Data Factory ليكون مرنًا وقابلاً للتخصيص، مما يسمح للمطورين بتسجيل مولدات ومحسّنات ومسارات دمج بيانات مخصصة لتلبية احتياجات المشروع. يمكن تشغيل الحلقة الذاتية بشكل دوري لضمان تحديث مجموعات البيانات وتحسينها باستمرار.

### مثال على الاستخدام:

```python
from hajeen_platform.services.data_intelligence.data_factory import AutonomousDataFactory
from hajeen_platform.services.data_intelligence.components import synthetic_data_generator, dataset_refiner, vector_store_ingestion_pipeline, MockLLM, MockVectorDBClient

# تهيئة المصنع وتسجيل المكونات
mock_llm = MockLLM()
factory = AutonomousDataFactory(llm=mock_llm)
factory.register_generator("synth_gen", synthetic_data_generator)
factory.register_refiner("cleaner", dataset_refiner)
factory.register_ingestion_pipeline("vector_ingest", vector_store_ingestion_pipeline)

# إعدادات الحلقة الذاتية
config = {
    "generator": "synth_gen",
    "generator_config": {"schema": {"name": "str", "value": "int"}, "count": 5},
    "refiner": "cleaner",
    "refiner_config": {"rules": ["remove_duplicates", "normalize_text"]},
    "ingestion_pipeline": "vector_ingest",
    "ingestion_config": {"vector_db_client": MockVectorDBClient()}
}

# تشغيل الحلقة الذاتية
final_dataset = await factory.run_autonomous_loop(config, iterations=3)
print(f"Final dataset after autonomous loop: {len(final_dataset)} items")
```

تهدف هذه المرحلة إلى أتمتة وتحسين جودة البيانات، مما يقلل من الجهد اليدوي ويزيد من كفاءة تدريب ونشر نماذج الذكاء الاصطناعي في Hajeen AI Platform.
