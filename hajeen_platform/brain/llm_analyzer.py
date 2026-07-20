import os
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

async def analyze_with_llm(user_request: str) -> LLMAnalysisResult:
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
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
        model="gpt-4o", # Using a capable model for structured output
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request}
        ],
        response_model=LLMAnalysisResult
    )
    return response.choices[0].message.content
