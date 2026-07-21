import os
import re
from typing import List, Literal

from openai import OpenAI
from pydantic import BaseModel


class LLMAnalysisResult(BaseModel):
    intent: Literal["question", "task", "creative", "analysis", "code", "research", "training", "data", "conversation", "planning"]
    complexity: Literal["simple", "medium", "complex", "enterprise"]
    domain: str
    sub_tasks: List[str]
    required_tools: List[str]
    suitable_models: List[str]
    final_objective: str


def _rule_based_analysis(user_request: str) -> LLMAnalysisResult:
    """تحليل قائم على القواعد عند عدم توفر LLM."""
    request_lower = user_request.lower()
    
    # كشف النية
    intent = "question"
    if any(k in request_lower for k in ["تدريب", "fine-tune", "ضبط دقيق", "train", "تعليم"]):
        intent = "training"
    elif any(k in request_lower for k in ["اكتب كود", "برمجة", "python", "javascript", "api", "دالة", "script", "كود"]):
        intent = "code"
    elif any(k in request_lower for k in ["ابحث", "research", "دراسة", "تقرير"]):
        intent = "research"
    elif any(k in request_lower for k in ["حلل", "تحليل", "قارن", "evaluate", "تقييم"]):
        intent = "analysis"
    elif any(k in request_lower for k in ["اكتب قصة", "أنشئ محتوى", "توليد", "generate", "إبداع"]):
        intent = "creative"
    elif any(k in request_lower for k in ["معالجة بيانات", "تنظيف", "dataset", "csv", "sql"]):
        intent = "data"
    elif any(k in request_lower for k in ["خطط", "plan", "خارطة طريق", "roadmap"]):
        intent = "planning"
    elif any(k in request_lower for k in ["مهمة", "أنجز", "نفذ", "do", "execute"]):
        intent = "task"
    
    # كشف التعقيد
    complexity = "simple"
    if any(k in request_lower for k in ["منصة كاملة", "نظام متكامل", "pipeline", "اعتمادية"]):
        complexity = "enterprise"
    elif any(k in request_lower for k in ["خطوات متعددة", "تسلسل", "ثم", "بعد ذلك", "وأيضاً", "قاعدة بيانات", "api"]):
        complexity = "complex"
    elif any(k in request_lower for k in ["مقارنة", "تحليل", "شرح مفصل", "خطوة بخطوة", "مثال"]):
        complexity = "medium"
    
    # كشف المجال
    domain = "general"
    if any(k in request_lower for k in ["نموذج لغوي", "llm", "embedding", "tokenizer", "نص", "لغة"]):
        domain = "nlp"
    elif any(k in request_lower for k in ["بيانات", "dataset", "قاعدة بيانات", "تنظيف", "csv", "sql"]):
        domain = "data"
    elif any(k in request_lower for k in ["rag", "استرجاع", "وثيقة", "pdf", "vector"]):
        domain = "rag"
    elif any(k in request_lower for k in ["وكيل", "agent", "أداة", "tool"]):
        domain = "agent"
    elif any(k in request_lower for k in ["عربي", "arabic", "لغة عربية"]):
        domain = "arabic"
    
    # المهام الفرعية - مخصصة حسب النية والتعقيد
    sub_tasks = []
    if intent == "training":
        sub_tasks = ["تحليل المتطلبات", "جمع البيانات", "تنظيف البيانات", "إعداد النموذج", "التدريب", "التقييم", "النشر"]
        complexity = "complex"
    elif complexity in ["complex", "enterprise"]:
        sub_tasks = ["تحليل المتطلبات", "تصميم الحل", "التنفيذ", "الاختبار", "النشر"]
    elif complexity == "medium":
        sub_tasks = ["تحليل", "المعالجة", "إنتاج النتيجة", "التحقق"]
    else:
        sub_tasks = ["تحليل الطلب", "تنفيذ الطلب", "مراجعة النتيجة"]
    
    # الأدوات المطلوبة
    required_tools = ["llm"]
    if intent == "code":
        required_tools.append("code_generator")
    if intent == "training":
        required_tools.extend(["data_loader", "training_pipeline"])
    if domain == "rag":
        required_tools.append("vector_search")
    
    # النماذج المناسبة
    suitable_models = ["gpt-4o", "claude-3-opus"]
    if domain == "arabic":
        suitable_models.insert(0, "aragpt")
    
    return LLMAnalysisResult(
        intent=intent,
        complexity=complexity,
        domain=domain,
        sub_tasks=sub_tasks,
        required_tools=required_tools,
        suitable_models=suitable_models,
        final_objective=user_request
    )


async def analyze_with_llm(user_request: str) -> LLMAnalysisResult:
    """تحليل طلب المستخدم - يستخدم LLM إن توفر، fallback قائم على القواعد."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return _rule_based_analysis(user_request)
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        )

        system_prompt = """
        أنت مساعد ذكاء اصطناعي متقدم مهمتك تحليل طلبات المستخدمين بدقة عالية.
        يجب عليك استخلاص النية الحقيقية، مستوى التعقيد، المجال، المهام الفرعية، الأدوات المطلوبة، والنماذج المناسبة من طلب المستخدم.
        يجب أن يكون الناتج بتنسيق JSON يتبع المخطط المحدد.

        النيات المحتملة: question, task, creative, analysis, code, research, training, data, conversation, planning
        مستويات التعقيد: simple, medium, complex, enterprise
        المجالات المحتملة: nlp, data, code, rag, agent, arabic, math, general (إذا لم يتطابق مع أي مجال آخر)
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request}
            ],
            response_model=LLMAnalysisResult
        )
        return response.choices[0].message.content
    except Exception:
        return _rule_based_analysis(user_request)
