"""
Decision Engine — محرك اتخاذ القرار
=====================================
جزء من HajeenBrainV3 Pipeline الموحّد.

يقوم بـ:
1. تقييم الخيارات المتاحة
2. اختيار النموذج/الأداة الأمثل
3. تحديد استراتيجية التنفيذ
4. إدارة الميزانية والجودة
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    MODEL_SELECTION = "model_selection"      # اختيار النموذج
    TOOL_SELECTION = "tool_selection"          # اختيار الأداة
    STRATEGY_SELECTION = "strategy_selection"  # اختيار الاستراتيجية
    FALLBACK = "fallback"                       # fallback
    REJECT = "reject"                           # رفض الطلب


class ModelCapability(Enum):
    REASONING = "reasoning"
    CREATIVITY = "creativity"
    SPEED = "speed"
    COST = "cost"
    ACCURACY = "accuracy"
    MULTILINGUAL = "multilingual"
    CODE = "code"
    MATHEMATICS = "mathematics"


@dataclass
class ModelOption:
    """خيار نموذج واحد."""
    model_id: str
    provider: str
    capabilities: Dict[ModelCapability, float]  # 0.0 to 1.0
    cost_per_token: float
    latency_ms: float
    context_window: int
    available: bool = True


@dataclass
class Decision:
    """قرار واحد."""
    decision_type: DecisionType
    selected_model: Optional[str] = None
    selected_tools: List[str] = field(default_factory=list)
    strategy: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    fallback_chain: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionContext:
    """سياق القرار."""
    query: str
    complexity: float  # 0.0 to 1.0
    required_capabilities: List[ModelCapability]
    budget_limit: Optional[float] = None
    latency_requirement_ms: Optional[float] = None
    previous_decisions: List[Decision] = field(default_factory=list)


class DecisionEngine:
    """
    محرك اتخاذ القرار — يختار النموذج والأدوات الأمثل.

    يستخدم ضمن HajeenBrainV3 Pipeline:
      Policy → Intent → Context → Reasoning → Planning → [Decision] → Execute
    """

    def __init__(self, llm_manager=None, model_registry=None):
        self.llm_manager = llm_manager
        self.model_registry = model_registry or self._default_registry()
        self.decision_history: List[Decision] = []
        logger.info("DecisionEngine initialized with %d models", len(self.model_registry))

    # ── Core Methods ──────────────────────────────────────────────────────

    async def decide(
        self,
        context: DecisionContext,
        available_models: Optional[List[str]] = None,
    ) -> Decision:
        """
        اتخاذ القرار الرئيسي.

        Args:
            context: سياق القرار (الاستعلام، التعقيد، المتطلبات)
            available_models: قائمة النماذج المتاحة (اختياري)
        """
        import time
        start = time.perf_counter()

        logger.info("Deciding: query_len=%d, complexity=%.2f", len(context.query), context.complexity)

        # 1. Filter available models
        models = self._filter_models(available_models)

        if not models:
            return Decision(
                decision_type=DecisionType.REJECT,
                confidence=1.0,
                reasoning="No models available",
            )

        # 2. Score each model
        scored_models = self._score_models(models, context)

        # 3. Select best model
        best_model = scored_models[0] if scored_models else None

        if not best_model:
            return Decision(
                decision_type=DecisionType.REJECT,
                confidence=1.0,
                reasoning="No suitable model found",
            )

        # 4. Build fallback chain
        fallback_chain = [m.model_id for m in scored_models[1:3]]

        # 5. Select tools if needed
        tools = self._select_tools(context, best_model)

        # 6. Determine strategy
        strategy = self._determine_strategy(context, best_model)

        elapsed = (time.perf_counter() - start) * 1000

        decision = Decision(
            decision_type=DecisionType.MODEL_SELECTION,
            selected_model=best_model.model_id,
            selected_tools=tools,
            strategy=strategy,
            confidence=scored_models[0][1] if scored_models else 0.5,
            reasoning=f"Selected {best_model.model_id} based on capability match and cost",
            fallback_chain=fallback_chain,
            estimated_cost=best_model.cost_per_token * len(context.query.split()) * 2,  # rough estimate
            estimated_latency_ms=best_model.latency_ms + elapsed,
            metadata={
                "all_scores": {m.model_id: score for m, score in scored_models},
                "decision_time_ms": elapsed,
            }
        )

        self.decision_history.append(decision)
        return decision

    # ── Model Scoring ────────────────────────────────────────────────────

    def _filter_models(
        self,
        available_models: Optional[List[str]],
    ) -> List[ModelOption]:
        """تصفية النماذج المتاحة."""
        if available_models is None:
            return [m for m in self.model_registry.values() if m.available]
        return [m for m in self.model_registry.values() if m.model_id in available_models and m.available]

    def _score_models(
        self,
        models: List[ModelOption],
        context: DecisionContext,
    ) -> List[Tuple[ModelOption, float]]:
        """تقييم النماذج وترتيبها."""
        scored = []

        for model in models:
            score = 0.0

            # Capability match (40%)
            for cap in context.required_capabilities:
                score += model.capabilities.get(cap, 0.0) * 0.4

            # Cost efficiency (20%)
            max_cost = max(m.cost_per_token for m in models) if models else 1.0
            score += (1.0 - model.cost_per_token / max_cost) * 0.2

            # Speed (20%)
            max_latency = max(m.latency_ms for m in models) if models else 1.0
            score += (1.0 - model.latency_ms / max_latency) * 0.2

            # Context window adequacy (20%)
            query_tokens = len(context.query.split())
            if model.context_window >= query_tokens * 2:
                score += 0.2
            else:
                score += (model.context_window / (query_tokens * 2)) * 0.2

            scored.append((model, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _select_tools(
        self,
        context: DecisionContext,
        model: ModelOption,
    ) -> List[str]:
        """اختيار الأدوات المناسبة."""
        tools = []

        # If query mentions specific tools
        query_lower = context.query.lower()
        tool_keywords = {
            "search": ["بحث", "search", "find", "ابحث"],
            "calculator": ["حساب", "calculate", "math", "رياضيات"],
            "code": ["code", "programming", "برمجة", "كود"],
            "database": ["database", "db", "قاعدة بيانات"],
        }

        for tool, keywords in tool_keywords.items():
            if any(kw in query_lower for kw in keywords):
                tools.append(tool)

        return tools

    def _determine_strategy(
        self,
        context: DecisionContext,
        model: ModelOption,
    ) -> str:
        """تحديد استراتيجية التنفيذ."""
        if context.complexity > 0.8:
            return "chain_of_thought"
        elif context.complexity > 0.5:
            return "step_by_step"
        else:
            return "direct"

    # ── Default Registry ────────────────────────────────────────────────

    def _default_registry(self) -> Dict[str, ModelOption]:
        """سجل النماذج الافتراضي."""
        return {
            "gpt-4": ModelOption(
                model_id="gpt-4",
                provider="openai",
                capabilities={
                    ModelCapability.REASONING: 0.95,
                    ModelCapability.CREATIVITY: 0.9,
                    ModelCapability.ACCURACY: 0.95,
                    ModelCapability.MULTILINGUAL: 0.9,
                    ModelCapability.CODE: 0.9,
                    ModelCapability.MATHEMATICS: 0.85,
                    ModelCapability.SPEED: 0.6,
                    ModelCapability.COST: 0.3,
                },
                cost_per_token=0.03,
                latency_ms=2000,
                context_window=8192,
            ),
            "gpt-3.5-turbo": ModelOption(
                model_id="gpt-3.5-turbo",
                provider="openai",
                capabilities={
                    ModelCapability.REASONING: 0.7,
                    ModelCapability.CREATIVITY: 0.75,
                    ModelCapability.ACCURACY: 0.75,
                    ModelCapability.MULTILINGUAL: 0.8,
                    ModelCapability.CODE: 0.7,
                    ModelCapability.MATHEMATICS: 0.6,
                    ModelCapability.SPEED: 0.9,
                    ModelCapability.COST: 0.8,
                },
                cost_per_token=0.002,
                latency_ms=800,
                context_window=4096,
            ),
            "local-llm": ModelOption(
                model_id="local-llm",
                provider="local",
                capabilities={
                    ModelCapability.REASONING: 0.5,
                    ModelCapability.CREATIVITY: 0.6,
                    ModelCapability.ACCURACY: 0.6,
                    ModelCapability.MULTILINGUAL: 0.4,
                    ModelCapability.CODE: 0.5,
                    ModelCapability.MATHEMATICS: 0.4,
                    ModelCapability.SPEED: 0.95,
                    ModelCapability.COST: 1.0,
                },
                cost_per_token=0.0,
                latency_ms=300,
                context_window=2048,
            ),
        }

    # ── History & Analytics ──────────────────────────────────────────────

    def get_decision_stats(self) -> Dict[str, Any]:
        """إحصائيات القرارات."""
        if not self.decision_history:
            return {}

        from collections import Counter
        model_counts = Counter(d.selected_model for d in self.decision_history if d.selected_model)

        return {
            "total_decisions": len(self.decision_history),
            "most_used_model": model_counts.most_common(1)[0] if model_counts else None,
            "avg_confidence": sum(d.confidence for d in self.decision_history) / len(self.decision_history),
            "rejection_rate": sum(1 for d in self.decision_history if d.decision_type == DecisionType.REJECT) / len(self.decision_history),
        }


# ── Singleton ─────────────────────────────────────────────────────────────

_decision_engine: Optional[DecisionEngine] = None


def get_decision_engine(llm_manager=None, model_registry=None) -> DecisionEngine:
    """الحصول على محرك القرار — Singleton."""
    global _decision_engine
    if _decision_engine is None:
        _decision_engine = DecisionEngine(llm_manager=llm_manager, model_registry=model_registry)
    return _decision_engine
