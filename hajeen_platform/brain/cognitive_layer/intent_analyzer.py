"""
Intent Analyzer — محلّل النية الحقيقية
======================================

يحلل نية المستخدم باستخدام استدلال النموذج، وليس مطابقة الكلمات المفتاحية.

يستخرج:
- النية الحقيقية (ما يريده المستخدم بالفعل)
- الأهداف الثانوية
- المتطلبات الضمنية
- درجة الثقة في التحليل
- البدائل المحتملة
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from hajeen_platform.core.llm import LLMManager

logger = logging.getLogger(__name__)


class IntentCategory(str, Enum):
    """فئات النية الرئيسية."""
    INFORMATION_SEEKING = "information_seeking"  # البحث عن معلومات
    TASK_EXECUTION = "task_execution"            # تنفيذ مهمة
    CREATIVE_GENERATION = "creative_generation"  # توليد محتوى إبداعي
    ANALYSIS_EVALUATION = "analysis_evaluation"  # تحليل وتقييم
    CODE_DEVELOPMENT = "code_development"        # تطوير برمجي
    LEARNING_TRAINING = "learning_training"      # التعلم والتدريب
    PLANNING_STRATEGY = "planning_strategy"      # التخطيط والاستراتيجية
    CONVERSATION = "conversation"                # محادثة عامة
    PROBLEM_SOLVING = "problem_solving"          # حل المشاكل


@dataclass
class Intent:
    """تمثيل النية المستخرجة."""
    intent_id: str
    category: IntentCategory
    primary_intent: str  # النية الأساسية بالكلمات
    secondary_intents: List[str]  # النيات الثانوية
    implicit_requirements: List[str]  # المتطلبات الضمنية
    confidence: float  # درجة الثقة (0-1)
    reasoning: str  # شرح الاستدلال
    alternative_interpretations: List[Dict[str, Any]]  # تفسيرات بديلة
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "category": self.category.value,
            "primary_intent": self.primary_intent,
            "secondary_intents": self.secondary_intents,
            "implicit_requirements": self.implicit_requirements,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "alternative_interpretations": self.alternative_interpretations,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class IntentAnalyzer:
    """
    محلّل النية باستخدام الاستدلال العميق.
    
    لا يعتمد على مطابقة الكلمات المفتاحية، بل على فهم اللغة الطبيعية.
    """

    def __init__(self, llm_manager: LLMManager) -> None:
        self.llm_manager = llm_manager
        self._intents_cache: Dict[str, Intent] = {}
        logger.info("IntentAnalyzer: initialized")

    async def analyze(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """
        تحليل نية المستخدم من الرسالة.
        
        الخطوات:
        1. إرسال الرسالة إلى LLM مع prompt متخصص
        2. استخراج النية الأساسية والثانوية
        3. تحديد المتطلبات الضمنية
        4. حساب درجة الثقة
        5. اقتراح تفسيرات بديلة
        """
        intent_id = str(uuid.uuid4())
        
        try:
            # بناء prompt متخصص لتحليل النية
            analysis_prompt = self._build_analysis_prompt(user_message, context)
            
            # استدعاء LLM للتحليل
            llm_response = await self.llm_manager.generate(
                prompt=analysis_prompt,
                model="gpt-4o",  # نموذج قوي للاستدلال
                temperature=0.3,  # درجة حرارة منخفضة للاستقرار
                max_tokens=1000,
            )
            
            # تحليل الاستجابة
            intent_data = self._parse_llm_response(llm_response)
            
            # بناء كائن Intent
            intent = Intent(
                intent_id=intent_id,
                category=IntentCategory[intent_data.get("category", "CONVERSATION")],
                primary_intent=intent_data.get("primary_intent", ""),
                secondary_intents=intent_data.get("secondary_intents", []),
                implicit_requirements=intent_data.get("implicit_requirements", []),
                confidence=float(intent_data.get("confidence", 0.7)),
                reasoning=intent_data.get("reasoning", ""),
                alternative_interpretations=intent_data.get("alternative_interpretations", []),
                metadata={"user_message": user_message, "context": context or {}},
            )
            
            # تخزين مؤقت
            self._intents_cache[intent_id] = intent
            
            logger.info(
                "intent_analyzer: analyzed message intent_id=%s category=%s confidence=%.3f",
                intent_id, intent.category.value, intent.confidence
            )
            
            return intent
        
        except Exception as e:
            logger.error("intent_analyzer: error analyzing message: %s", e, exc_info=True)
            # استجابة احتياطية
            return Intent(
                intent_id=intent_id,
                category=IntentCategory.CONVERSATION,
                primary_intent="محادثة عامة",
                secondary_intents=[],
                implicit_requirements=[],
                confidence=0.5,
                reasoning="فشل التحليل، استجابة احتياطية",
                alternative_interpretations=[],
                metadata={"error": str(e)},
            )

    def _build_analysis_prompt(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """بناء prompt متخصص لتحليل النية."""
        context_str = ""
        if context:
            context_str = f"\n\nالسياق:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        
        return f"""أنت محلّل نية متقدم. حلّل الرسالة التالية واستخرج النية الحقيقية للمستخدم.

الرسالة:
"{user_message}"{context_str}

قم بالتحليل التالي:

1. **النية الأساسية**: ما يريده المستخدم بالفعل (بجملة واحدة واضحة)
2. **فئة النية**: اختر من: INFORMATION_SEEKING, TASK_EXECUTION, CREATIVE_GENERATION, ANALYSIS_EVALUATION, CODE_DEVELOPMENT, LEARNING_TRAINING, PLANNING_STRATEGY, CONVERSATION, PROBLEM_SOLVING
3. **النيات الثانوية**: أهداف إضافية قد يكون لديها المستخدم (قائمة)
4. **المتطلبات الضمنية**: ما يحتاجه المستخدم ولم يقله صراحة (قائمة)
5. **درجة الثقة**: من 0 إلى 1 (كم أنت متأكد من هذا التحليل)
6. **الاستدلال**: شرح سبب اختيارك لهذه النية
7. **التفسيرات البديلة**: تفسيرات أخرى محتملة للرسالة (قائمة مع احتمالية كل منها)

أرجع الإجابة بصيغة JSON فقط:
{{
  "primary_intent": "...",
  "category": "...",
  "secondary_intents": [...],
  "implicit_requirements": [...],
  "confidence": 0.85,
  "reasoning": "...",
  "alternative_interpretations": [
    {{"interpretation": "...", "probability": 0.1}},
    ...
  ]
}}
"""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """تحليل استجابة LLM واستخراج البيانات."""
        try:
            # محاولة استخراج JSON من الاستجابة
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                return data
        except json.JSONDecodeError:
            logger.warning("intent_analyzer: failed to parse JSON from LLM response")
        
        # استجابة احتياطية
        return {
            "primary_intent": "محادثة عامة",
            "category": "CONVERSATION",
            "secondary_intents": [],
            "implicit_requirements": [],
            "confidence": 0.5,
            "reasoning": "فشل تحليل الاستجابة",
            "alternative_interpretations": [],
        }

    def get_intent(self, intent_id: str) -> Optional[Intent]:
        """الحصول على نية محفوظة."""
        return self._intents_cache.get(intent_id)

    def list_intents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """قائمة بآخر النيات المحللة."""
        intents = list(self._intents_cache.values())
        intents.sort(key=lambda i: i.created_at, reverse=True)
        return [i.to_dict() for i in intents[:limit]]


# Singleton
_intent_analyzer: Optional[IntentAnalyzer] = None


def get_intent_analyzer(llm_manager: Optional[LLMManager] = None) -> IntentAnalyzer:
    """الحصول على instance من IntentAnalyzer."""
    global _intent_analyzer
    if _intent_analyzer is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _intent_analyzer = IntentAnalyzer(llm_manager)
    return _intent_analyzer
