"""
Cognitive Layer — طبقة الإدراك المتقدمة
======================================

تتكون من:
1. Intent Analyzer — محلّل النية
2. Goal Analyzer — محلّل الأهداف
3. Context Analyzer — محلّل السياق
4. Reasoning Engine — محرك الاستدلال
5. Planner — المخطط الديناميكي

جميع المكونات تستخدم الاستدلال العميق وليس مطابقة الكلمات المفتاحية.
"""

from .intent_analyzer import (
    IntentAnalyzer,
    Intent,
    IntentCategory,
    get_intent_analyzer,
)

from .context_analyzer import (
    ContextAnalyzer,
    ContextAnalysis,
    get_context_analyzer,
)

from .reasoning_engine import (
    ReasoningEngine,
    ReasoningResult,
    ReasoningStrategy,
    get_reasoning_engine,
)

__all__ = [
    "IntentAnalyzer",
    "Intent",
    "IntentCategory",
    "get_intent_analyzer",
    "ContextAnalyzer",
    "ContextAnalysis",
    "get_context_analyzer",
    "ReasoningEngine",
    "ReasoningResult",
    "ReasoningStrategy",
    "get_reasoning_engine",
]
