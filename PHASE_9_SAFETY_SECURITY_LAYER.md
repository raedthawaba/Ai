# المرحلة التاسعة: تطوير Safety & Security Layer

تركز هذه المرحلة على تعزيز أمان وسلامة Hajeen AI Platform من خلال بناء طبقة قوية لإدارة السياسات الأمنية. الهدف هو حماية النظام من التهديدات المحتملة مثل حقن الأوامر (Prompt Injection)، والوصول غير المصرح به للأدوات، وضمان التزام المحتوى بمعايير السلامة.

## المكونات الرئيسية المضافة:

### 1. Policy Engine (`policy_engine.py`)
- **الوظيفة:** المحرك المركزي لتعريف وتطبيق السياسات الأمنية عبر النظام. يسمح بتسجيل وظائف السياسات المختلفة وتقييم السياقات مقابل هذه السياسات.
- **القدرات:**
    - **تسجيل السياسات:** يمكن للمطورين تسجيل دوال سياسة مخصصة للتعامل مع أنواع مختلفة من التهديدات أو متطلبات الأمان.
    - **التقييم (Evaluate):** يقوم بتقييم سياق معين (مثل طلب وكيل، محتوى، أو استخدام أداة) مقابل جميع السياسات المسجلة، ويعيد نتائج مفصلة لكل سياسة.
    - **الإنفاذ (Enforce):** يوفر طريقة بسيطة لتحديد ما إذا كان الإجراء مسموحًا به بناءً على جميع السياسات. إذا رفضت أي سياسة الإجراء، يتم رفضه ككل.

### 2. أمثلة على السياسات المطبقة (`policy_engine.py`):
- **`prompt_injection_policy`:** يكتشف ويمنع محاولات حقن الأوامر التي تهدف إلى تجاوز تعليمات النظام أو استخراج معلومات حساسة.
- **`tool_permission_policy`:** يتحقق من أن الوكيل لديه الأذونات اللازمة لاستخدام أداة معينة، مما يمنع الوصول غير المصرح به للأدوات الحساسة.
- **`content_moderation_policy`:** يقوم بفحص المحتوى بحثًا عن أي انتهاكات لمعايير السلامة، مثل خطاب الكراهية أو الأنشطة غير القانونية.

## التكامل والتشغيل:

تم تصميم Policy Engine ليكون نقطة تحكم مركزية للأمان، حيث يمكن دمجها في مسارات عمل الوكلاء، ومعالجة المدخلات، ومراقبة المخرجات. هذا يضمن أن جميع التفاعلات داخل Hajeen AI Platform تتوافق مع السياسات الأمنية المحددة.

### مثال على الاستخدام:

```python
from hajeen_platform.services.security.policy_engine import PolicyEngine, prompt_injection_policy, tool_permission_policy

# تهيئة المحرك وتسجيل السياسات
engine = PolicyEngine()
engine.register_policy("prompt_injection_check", prompt_injection_policy)
engine.register_policy("tool_access_check", tool_permission_policy)

# سياق مثال لتقييمه
context_to_evaluate = {
    "prompt": "Please summarize the document.",
    "agent_id": "reporting_agent",
    "tool_name": "document_reader"
}

# إنفاذ السياسات
if engine.enforce(context_to_evaluate):
    print("Action allowed: All policies passed.")
else:
    print("Action denied: One or more policies failed.")

# تقييم مفصل
detailed_results = engine.evaluate(context_to_evaluate)
print(detailed_results)
```

تهدف هذه المرحلة إلى توفير بيئة آمنة وموثوقة لتشغيل تطبيقات الذكاء الاصطناعي، وحماية المستخدمين والنظام من السلوكيات الضارة أو غير المرغوب فيها.
