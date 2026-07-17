"""
Goal Manager — محوّل الطلبات إلى أهداف قابلة للتنفيذ
======================================================
    يستخرج الهدف النهائي للمستخدم، النية، مستوى التعقيد، المجال، والمهام المطلوبة.
    يعتمد على LLM لاتخاذ القرار — يستخدم اللغة النموذجية للتحليل والاستنتاج.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from hajeen_platform.brain.llm_analyzer import analyze_with_llm, LLMAnalysisResult

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
    REASONING = "reasoning"         # استدلال / تقييم


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
        llm_analysis = await analyze_with_llm(user_request)

        intent = IntentType(llm_analysis.intent)
        complexity = ComplexityLevel(llm_analysis.complexity)
        domain = llm_analysis.domain
        sub_tasks = llm_analysis.sub_tasks
        required_tools = llm_analysis.required_tools
        suitable_models = llm_analysis.suitable_models
        final_objective = llm_analysis.final_objective

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
