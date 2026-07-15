"""
Decision Engine — محرك القرار المستقل
======================================
يقرر أي نموذج / أداة / مصدر يُستخدم لكل مهمة.
القرارات لا يحددها LLM — بل قواعد محددة + بيانات الأداء التاريخية.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .goal_manager import Goal, IntentType, ComplexityLevel

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    LOCAL_MODEL = "local_model"     # نموذج محلي (Ollama, llama.cpp)
    CLOUD_MODEL = "cloud_model"     # نموذج سحابي (OpenAI, Qwen API)
    RAG = "rag"                     # استرجاع من قاعدة المعرفة
    WEB_SEARCH = "web_search"       # البحث على الإنترنت
    TOOL = "tool"                   # أداة خارجية
    MULTI_MODEL = "multi_model"     # تعاون عدة نماذج
    CACHE = "cache"                 # نتيجة مخزّنة مسبقاً


@dataclass
class Decision:
    """قرار الـ Decision Engine لمهمة معينة."""
    task_id: str
    resource_type: ResourceType
    primary_model: str
    fallback_model: Optional[str]
    use_rag: bool
    use_web: bool
    use_multi_model: bool
    collaborating_models: List[str]
    estimated_cost_tokens: int
    confidence: float
    reasoning: str
    metadata: Dict[str, Any]
    decided_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "resource_type": self.resource_type,
            "primary_model": self.primary_model,
            "fallback_model": self.fallback_model,
            "use_rag": self.use_rag,
            "use_web": self.use_web,
            "use_multi_model": self.use_multi_model,
            "collaborating_models": self.collaborating_models,
            "estimated_cost_tokens": self.estimated_cost_tokens,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class DecisionEngine:
    """
    المحرك المركزي لاتخاذ القرار.

    يعتمد على:
    - قواعد محددة مسبقاً
    - بيانات أداء النماذج التاريخية (Model Performance DB)
    - السياسات المعمول بها (Policy Engine)
    - حالة الموارد المتاحة
    """

    # قواعد اختيار النموذج بناءً على النية
    MODEL_RULES: Dict[str, Dict[str, Any]] = {
        "code": {
            "primary": "qwen2.5-coder-7b",
            "fallback": "openai/gpt-4o",
            "use_rag": False,
        },
        "arabic": {
            "primary": "qwen2.5-7b-arabic",
            "fallback": "openai/gpt-4o",
            "use_rag": True,
        },
        "training": {
            "primary": "local_pipeline",
            "fallback": None,
            "use_rag": True,
        },
        "rag": {
            "primary": "ollama/llama3",
            "fallback": "openai/gpt-4o",
            "use_rag": True,
        },
        "math": {
            "primary": "qwen2.5-math-7b",
            "fallback": "openai/gpt-4o",
            "use_rag": False,
        },
        "general": {
            "primary": "ollama/llama3",
            "fallback": "openai/gpt-4o",
            "use_rag": False,
        },
    }

    # حدود التكلفة المسموحة
    COST_LIMITS = {
        ComplexityLevel.SIMPLE: 1000,     # tokens
        ComplexityLevel.MEDIUM: 5000,
        ComplexityLevel.COMPLEX: 20000,
        ComplexityLevel.ENTERPRISE: 100000,
    }

    def __init__(self, performance_db=None, policy_engine=None) -> None:
        self._performance_db = performance_db
        self._policy_engine = policy_engine
        self._decisions: List[Decision] = []

    async def decide(
        self,
        task_id: str,
        goal: Goal,
        task_name: str,
        context: Optional[Dict] = None,
    ) -> Decision:
        """اتخاذ القرار لمهمة محددة."""
        domain = goal.domain
        intent = goal.intent
        complexity = goal.complexity

        # 1. اختيار الموارد بناءً على القواعد
        rule = self.MODEL_RULES.get(domain, self.MODEL_RULES["general"])
        primary_model = rule["primary"]
        fallback_model = rule.get("fallback")
        use_rag = rule.get("use_rag", False)

        # 2. تحسين بيانات الأداء التاريخية
        if self._performance_db:
            best = await self._performance_db.get_best_model_for(intent, domain)
            if best and best["success_rate"] > 0.8:
                primary_model = best["model_id"]

        # 3. تطبيق السياسات
        use_web = await self._should_use_web(intent, task_name)
        use_multi_model = complexity in (ComplexityLevel.COMPLEX, ComplexityLevel.ENTERPRISE)
        collaborating = self._get_collaborating_models(intent, complexity, primary_model) if use_multi_model else []

        # 4. تحديد نوع المورد
        resource_type = self._determine_resource_type(primary_model, use_rag, use_web, use_multi_model)

        # 5. تقدير التكلفة
        cost_limit = self.COST_LIMITS[complexity]
        estimated_cost = min(cost_limit, self._estimate_cost(intent, complexity))

        # 6. بناء مبرر القرار
        reasoning = self._build_reasoning(
            primary_model, use_rag, use_web, use_multi_model,
            collaborating, domain, complexity
        )

        decision = Decision(
            task_id=task_id,
            resource_type=resource_type,
            primary_model=primary_model,
            fallback_model=fallback_model,
            use_rag=use_rag,
            use_web=use_web,
            use_multi_model=use_multi_model,
            collaborating_models=collaborating,
            estimated_cost_tokens=estimated_cost,
            confidence=0.88,
            reasoning=reasoning,
            metadata={
                "domain": domain,
                "intent": intent,
                "complexity": complexity,
            },
            decided_at=time.time(),
        )
        self._decisions.append(decision)
        logger.info(
            "decision_engine: task=%s model=%s rag=%s web=%s multi=%s",
            task_id, primary_model, use_rag, use_web, use_multi_model
        )
        return decision

    async def _should_use_web(self, intent: IntentType, task_name: str) -> bool:
        web_intents = {IntentType.RESEARCH}
        if intent in web_intents:
            return True
        web_keywords = ["ابحث", "أحدث", "اليوم", "أخبار", "search", "latest"]
        return any(kw in task_name for kw in web_keywords)

    def _get_collaborating_models(
        self, intent: IntentType, complexity: ComplexityLevel, primary: str
    ) -> List[str]:
        if complexity == ComplexityLevel.ENTERPRISE:
            models = ["qwen2.5-72b", "openai/gpt-4o", "ollama/llama3"]
        elif complexity == ComplexityLevel.COMPLEX:
            models = ["qwen2.5-7b", "ollama/llama3"]
        else:
            models = []
        return [m for m in models if m != primary]

    def _determine_resource_type(
        self, model: str, use_rag: bool, use_web: bool, use_multi: bool
    ) -> ResourceType:
        if use_multi:
            return ResourceType.MULTI_MODEL
        if use_web:
            return ResourceType.WEB_SEARCH
        if use_rag:
            return ResourceType.RAG
        if "openai" in model or "cloud" in model:
            return ResourceType.CLOUD_MODEL
        return ResourceType.LOCAL_MODEL

    def _estimate_cost(self, intent: IntentType, complexity: ComplexityLevel) -> int:
        base = {
            ComplexityLevel.SIMPLE: 500,
            ComplexityLevel.MEDIUM: 2000,
            ComplexityLevel.COMPLEX: 8000,
            ComplexityLevel.ENTERPRISE: 30000,
        }
        return base[complexity]

    def _build_reasoning(
        self, model: str, rag: bool, web: bool, multi: bool,
        collaborating: List[str], domain: str, complexity: ComplexityLevel
    ) -> str:
        parts = [f"النموذج الأساسي: {model}"]
        if rag:
            parts.append("استخدام RAG لتحسين الدقة")
        if web:
            parts.append("البحث على الإنترنت للمعلومات الحديثة")
        if multi:
            parts.append(f"تعاون متعدد النماذج: {', '.join(collaborating)}")
        parts.append(f"المجال: {domain} | التعقيد: {complexity}")
        return " | ".join(parts)

    def get_recent_decisions(self, limit: int = 10) -> List[Dict]:
        return [d.to_dict() for d in self._decisions[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        if not self._decisions:
            return {"total": 0}
        local = sum(1 for d in self._decisions if d.resource_type == ResourceType.LOCAL_MODEL)
        cloud = sum(1 for d in self._decisions if d.resource_type == ResourceType.CLOUD_MODEL)
        multi = sum(1 for d in self._decisions if d.use_multi_model)
        return {
            "total": len(self._decisions),
            "local_model": local,
            "cloud_model": cloud,
            "multi_model": multi,
            "local_ratio": round(local / len(self._decisions), 2),
        }


# Singleton
_engine: Optional[DecisionEngine] = None


def get_decision_engine() -> DecisionEngine:
    global _engine
    if _engine is None:
        _engine = DecisionEngine()
    return _engine
