"""
Goal Manager — محوّل الطلبات إلى أهداف قابلة للتنفيذ
======================================================
يستخرج الهدف النهائي للمستخدم، النية، مستوى التعقيد، المجال، والمهام المطلوبة.
لا يعتمد على LLM لاتخاذ القرار — يستخدم اللغة النموذجية فقط للتحليل.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    QUESTION = "question"           # سؤال / استفسار
    TASK = "task"                   # مهمة محددة
    CREATIVE = "creative"           # إبداع / توليد محتوى
    ANALYSIS = "analysis"           # تحليل
    CODE = "code"                   # برمجة
    RESEARCH = "research"           # بحث
    TRAINING = "training"           # تدريب نموذج
    DATA = "data"                   # معالجة بيانات
    CONVERSATION = "conversation"   # محادثة عامة
    PLANNING = "planning"           # تخطيط


class ComplexityLevel(str, Enum):
    SIMPLE = "simple"       # إجابة مباشرة — نموذج واحد
    MEDIUM = "medium"       # يحتاج تخطيط — 2-3 خطوات
    COMPLEX = "complex"     # متعدد الخطوات — قد يحتاج وكلاء
    ENTERPRISE = "enterprise"  # تسلسل كامل + وكلاء + موارد


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "nlp": ["نموذج لغوي", "llm", "تدريب", "fine-tuning", "ضبط دقيق", "embedding", "tokenizer", "نص", "لغة"],
    "data": ["بيانات", "dataset", "قاعدة بيانات", "تنظيف", "معالجة", "تحليل", "إحصاء", "csv", "sql"],
    "code": ["كود", "برمجة", "python", "javascript", "api", "خطأ", "bug", "debug", "دالة", "كلاس"],
    "rag": ["rag", "استرجاع", "وثيقة", "pdf", "بحث", "vector", "مستند", "قاعدة معرفة"],
    "agent": ["وكيل", "agent", "أداة", "tool", "automation", "خطوات متعددة", "مهام"],
    "arabic": ["عربي", "arabic", "لغة عربية", "نص عربي", "محتوى عربي"],
    "math": ["رياضيات", "حساب", "معادلة", "احتمال", "إحصاء", "حل"],
    "general": [],
}

INTENT_PATTERNS: Dict[IntentType, List[str]] = {
    IntentType.TRAINING: ["تدريب", "fine-tune", "ضبط دقيق", "train", "تعليم نموذج"],
    IntentType.CODE: ["اكتب كود", "برمجة", "python", "javascript", "api", "دالة", "script"],
    IntentType.RESEARCH: ["ابحث", "research", "دراسة", "تقرير", "معلومات عن", "ماذا تعرف عن"],
    IntentType.ANALYSIS: ["حلل", "تحليل", "قارن", "evaluate", "تقييم", "فرق"],
    IntentType.CREATIVE: ["اكتب قصة", "أنشئ محتوى", "توليد", "generate", "إبداع", "شعر"],
    IntentType.DATA: ["معالجة بيانات", "تنظيف", "dataset", "csv", "sql", "استعلام"],
    IntentType.PLANNING: ["خطط", "plan", "خارطة طريق", "roadmap", "مراحل", "خطوات"],
    IntentType.QUESTION: ["ما هو", "ما هي", "كيف", "لماذا", "متى", "أين", "من هو"],
    IntentType.CONVERSATION: [],
}

COMPLEXITY_INDICATORS = {
    ComplexityLevel.ENTERPRISE: [
        "منصة كاملة", "نظام متكامل", "multiple models", "وكلاء متعددة",
        "pipeline", "تدريب", "نشر", "production", "اعتمادية", "scale"
    ],
    ComplexityLevel.COMPLEX: [
        "خطوات متعددة", "تسلسل", "pipeline", "ثم", "بعد ذلك", "وأيضاً",
        "كما أريد", "إضافة إلى", "قاعدة بيانات", "api"
    ],
    ComplexityLevel.MEDIUM: [
        "مقارنة", "تحليل", "شرح مفصل", "خطوة بخطوة", "مثال", "كيف"
    ],
}


@dataclass
class Goal:
    goal_id: str
    original_request: str
    final_objective: str
    intent: IntentType
    complexity: ComplexityLevel
    domain: str
    sub_tasks: List[str]
    required_tools: List[str]
    suitable_models: List[str]
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "original_request": self.original_request,
            "final_objective": self.final_objective,
            "intent": self.intent,
            "complexity": self.complexity,
            "domain": self.domain,
            "sub_tasks": self.sub_tasks,
            "required_tools": self.required_tools,
            "suitable_models": self.suitable_models,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class GoalManager:
    """
    يحوّل أي طلب مستخدم إلى هدف منظّم قابل للتنفيذ.

    الخطوات:
    1. تحليل النص لاستخراج النية
    2. تحديد مستوى التعقيد
    3. تحديد المجال
    4. توليد قائمة المهام الفرعية
    5. اقتراح الأدوات والنماذج
    """

    def __init__(self) -> None:
        self._goals: Dict[str, Goal] = {}

    async def analyze(self, user_request: str, context: Optional[Dict] = None) -> Goal:
        """تحليل الطلب وتوليد الهدف."""
        text_lower = user_request.lower()

        intent = self._detect_intent(text_lower)
        complexity = self._detect_complexity(text_lower)
        domain = self._detect_domain(text_lower)
        sub_tasks = self._generate_sub_tasks(intent, complexity, domain, user_request)
        required_tools = self._suggest_tools(intent, domain, sub_tasks)
        suitable_models = self._suggest_models(intent, complexity, domain)
        final_objective = self._extract_objective(user_request, intent)

        goal = Goal(
            goal_id=str(uuid.uuid4()),
            original_request=user_request,
            final_objective=final_objective,
            intent=intent,
            complexity=complexity,
            domain=domain,
            sub_tasks=sub_tasks,
            required_tools=required_tools,
            suitable_models=suitable_models,
            confidence=0.85,
            metadata={"context": context or {}},
        )
        self._goals[goal.goal_id] = goal
        logger.info(
            "goal_manager: intent=%s complexity=%s domain=%s tasks=%d",
            intent, complexity, domain, len(sub_tasks)
        )
        return goal

    def _detect_intent(self, text: str) -> IntentType:
        scores: Dict[IntentType, int] = {t: 0 for t in IntentType}
        for intent, patterns in INTENT_PATTERNS.items():
            for p in patterns:
                if p in text:
                    scores[intent] += 1
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else IntentType.CONVERSATION

    def _detect_complexity(self, text: str) -> ComplexityLevel:
        for level in [ComplexityLevel.ENTERPRISE, ComplexityLevel.COMPLEX, ComplexityLevel.MEDIUM]:
            for indicator in COMPLEXITY_INDICATORS[level]:
                if indicator in text:
                    return level
        return ComplexityLevel.SIMPLE

    def _detect_domain(self, text: str) -> str:
        scores: Dict[str, int] = {d: 0 for d in DOMAIN_KEYWORDS}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[domain] += 1
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "general"

    def _generate_sub_tasks(
        self, intent: IntentType, complexity: ComplexityLevel,
        domain: str, request: str
    ) -> List[str]:
        tasks: List[str] = []

        if intent == IntentType.TRAINING:
            tasks = [
                "جمع البيانات وفحصها",
                "تنظيف البيانات وإزالة التكرار",
                "تحليل جودة البيانات",
                "إعداد dataset للتدريب",
                "اختيار النموذج الأساسي",
                "تهيئة بيئة التدريب",
                "تنفيذ التدريب / Fine-tuning",
                "تقييم النموذج",
                "نشر النموذج",
                "مراقبة الأداء",
            ]
        elif intent == IntentType.CODE:
            tasks = [
                "تحليل المتطلبات",
                "تصميم البنية",
                "كتابة الكود",
                "اختبار الوظائف",
                "مراجعة وتحسين الكود",
            ]
        elif intent == IntentType.RESEARCH:
            tasks = [
                "تحديد نطاق البحث",
                "جمع المصادر والمراجع",
                "تحليل المعلومات",
                "تلخيص النتائج",
                "تقديم التوصيات",
            ]
        elif intent == IntentType.ANALYSIS:
            tasks = [
                "جمع البيانات المطلوبة",
                "تحليل الأنماط",
                "المقارنة والتقييم",
                "استخلاص النتائج",
            ]
        elif intent == IntentType.DATA:
            tasks = [
                "تحميل البيانات",
                "فحص جودة البيانات",
                "تنظيف وتحويل البيانات",
                "تخزين النتائج",
            ]
        elif complexity == ComplexityLevel.SIMPLE:
            tasks = ["معالجة الطلب مباشرةً", "تقديم الإجابة"]
        else:
            tasks = ["تحليل الطلب", "تخطيط الخطوات", "التنفيذ", "مراجعة النتائج"]

        return tasks

    def _suggest_tools(self, intent: IntentType, domain: str, tasks: List[str]) -> List[str]:
        tools: List[str] = ["hajeen_brain"]
        if domain in ("nlp", "training"):
            tools += ["training_pipeline", "dataset_builder", "model_evaluator"]
        if domain == "rag":
            tools += ["vector_search", "document_loader", "rag_engine"]
        if domain == "code":
            tools += ["code_executor", "syntax_checker"]
        if domain == "data":
            tools += ["data_cleaner", "quality_scorer"]
        if intent == IntentType.RESEARCH:
            tools += ["web_search", "summarizer"]
        return list(dict.fromkeys(tools))

    def _suggest_models(self, intent: IntentType, complexity: ComplexityLevel, domain: str) -> List[str]:
        models: List[str] = []
        if domain == "arabic" or domain == "nlp":
            models.append("qwen2.5-7b")
        if complexity in (ComplexityLevel.COMPLEX, ComplexityLevel.ENTERPRISE):
            models += ["qwen2.5-72b", "openai/gpt-4o"]
        if intent == IntentType.CODE:
            models.append("qwen2.5-coder-7b")
        models += ["ollama/llama3", "hajeen-local"]
        return list(dict.fromkeys(models))

    def _extract_objective(self, request: str, intent: IntentType) -> str:
        mapping = {
            IntentType.TRAINING: "تدريب وتحسين نموذج لغوي",
            IntentType.CODE: "كتابة وتطوير كود برمجي",
            IntentType.RESEARCH: "بحث وجمع معلومات شاملة",
            IntentType.ANALYSIS: "تحليل وتقييم البيانات أو المفاهيم",
            IntentType.CREATIVE: "توليد محتوى إبداعي",
            IntentType.DATA: "معالجة وتنظيف البيانات",
            IntentType.PLANNING: "وضع خطة تفصيلية",
            IntentType.QUESTION: "الإجابة على السؤال",
            IntentType.CONVERSATION: "المحادثة والتفاعل",
            IntentType.TASK: "تنفيذ المهمة المطلوبة",
        }
        base = mapping.get(intent, "تلبية طلب المستخدم")
        # اقتطع الطلب الأصلي للتوضيح
        snippet = request[:80] + "..." if len(request) > 80 else request
        return f"{base}: {snippet}"

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def list_goals(self) -> List[Dict]:
        return [g.to_dict() for g in self._goals.values()]


# Singleton
_goal_manager: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager
