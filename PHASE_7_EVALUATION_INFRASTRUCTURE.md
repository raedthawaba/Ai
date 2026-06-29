# المرحلة السابعة: تطوير Evaluation Infrastructure Framework

تركز هذه المرحلة على بناء بنية تحتية شاملة لتقييم أداء نظام Hajeen AI Platform. الهدف هو ضمان جودة المخرجات، دقة الوكلاء، وموثوقية النظام بشكل عام من خلال قياسات ومقاييس أداء دقيقة ومؤتمتة.

## المكونات الرئيسية المضافة:

### 1. Evaluation Engine (`evaluation_engine.py`)
- **الوظيفة:** المحرك الأساسي لتشغيل عمليات التقييم المختلفة. يقوم بتسجيل المقاييس (Metrics) والمعايير (Benchmarks) وتشغيلها على نتائج الوكلاء أو النظام ككل.
- **القدرات:**
    - تسجيل المقاييس المخصصة (مثل اكتشاف الهلوسة، معدل نجاح الوكيل، زمن الاستجابة).
    - تسجيل المعايير (Benchmarks) التي يمكن تشغيلها بشكل دوري لتقييم الأداء العام.
    - تقييم نتائج وكيل واحد مقابل مجموعة من المقاييس.
    - تشغيل جميع المعايير المسجلة تلقائيًا.

### 2. Metrics Module (`metrics.py`)
- **الوظيفة:** يحتوي على تعريفات لمقاييس التقييم المختلفة التي يمكن استخدامها بواسطة Evaluation Engine.
- **المقاييس المطبقة حاليًا (أمثلة):**
    - `hallucination_metric`: لتقييم مدى وجود هلوسة في مخرجات الوكيل.
    - `agent_success_rate_metric`: لقياس معدل نجاح الوكيل في تحقيق أهدافه.
    - `latency_metric`: لقياس زمن الاستجابة الكلي للوكيل.
    - `tool_accuracy_metric`: لتقييم دقة استخدام الوكيل للأدوات المتاحة.

## التكامل والتشغيل:

تم تصميم Evaluation Engine ليكون مرنًا وقابلاً للتوسع، مما يسمح بإضافة مقاييس ومعايير جديدة بسهولة. يمكن استدعاء المحرك لتقييم نتائج الوكلاء بعد كل عملية تنفيذ، أو لتشغيل مجموعة من المعايير بشكل دوري لضمان استمرارية الأداء.

### مثال على الاستخدام:

```python
from hajeen_platform.services.evaluation.evaluation_engine import EvaluationEngine
from hajeen_platform.services.evaluation.metrics import hallucination_metric, agent_success_rate_metric
from hajeen_platform.services.agents.base_agent import AgentResult, AgentContext

# تهيئة المحرك وتسجيل المقاييس
engine = EvaluationEngine()
engine.register_metric("hallucination", hallucination_metric)
engine.register_metric("success_rate", agent_success_rate_metric)

# مثال على نتيجة وكيل
mock_result = AgentResult(
    success=True,
    output="The AI model provided a correct answer.",
    context=AgentContext(goal="answer question")
)

# تقييم النتيجة
eval_results = await engine.evaluate_agent_result(mock_result)
print(eval_results)
# {'hallucination': {'score': 0.9, 'detected': False}, 'success_rate': {'score': 1.0, 'success': True}}
```

تهدف هذه المرحلة إلى توفير رؤية واضحة حول أداء النظام، مما يمكن المطورين من تحديد نقاط الضعف وتحسينها بشكل مستمر، وضمان موثوقية واستقرار Hajeen AI Platform.
