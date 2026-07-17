"""
Unit Tests — Cognitive Layer (Phase 2 Complete)
===============================================
يختبر:
- IntentAnalyzer: استخراج النية
- ContextAnalyzer: تحليل السياق وبحث الذاكرة الدلالي
- ReasoningEngine: الاستدلال العميق
"""
from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ── IntentAnalyzer Tests ────────────────────────────────────────────────────

class TestIntentAnalyzer:
    """اختبارات محلل النية."""

    def _make_analyzer(self):
        from hajeen_platform.brain.cognitive_layer.intent_analyzer import (
            IntentAnalyzer, IntentCategory,
        )
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='''
{
  "primary_intent": "كتابة دالة Python لفرز قائمة",
  "category": "code_development",
  "secondary_intents": ["شرح الخوارزمية"],
  "implicit_requirements": ["كود قابل للقراءة", "تعليقات"],
  "confidence": 0.92,
  "reasoning": "الطلب يتضمن مصطلحات برمجية واضحة",
  "alternative_interpretations": []
}''')
        return IntentAnalyzer(llm_manager=llm_mock), IntentCategory

    def test_init(self):
        analyzer, _ = self._make_analyzer()
        assert analyzer is not None
        assert hasattr(analyzer, "analyze")

    @pytest.mark.asyncio
    async def test_analyze_code_request(self):
        analyzer, IntentCategory = self._make_analyzer()
        intent = await analyzer.analyze("اكتب دالة Python لفرز قائمة")
        assert intent is not None
        assert intent.intent_id
        assert intent.confidence >= 0.0
        assert intent.confidence <= 1.0
        assert intent.primary_intent
        assert isinstance(intent.secondary_intents, list)
        assert isinstance(intent.implicit_requirements, list)

    @pytest.mark.asyncio
    async def test_analyze_returns_intent_object(self):
        analyzer, _ = self._make_analyzer()
        intent = await analyzer.analyze("ما هو الذكاء الاصطناعي؟")
        assert hasattr(intent, "intent_id")
        assert hasattr(intent, "category")
        assert hasattr(intent, "primary_intent")
        assert hasattr(intent, "confidence")
        assert hasattr(intent, "reasoning")

    @pytest.mark.asyncio
    async def test_analyze_with_context(self):
        analyzer, _ = self._make_analyzer()
        intent = await analyzer.analyze(
            "اكتب كوداً",
            context={"session_id": "test-123", "history": ["مرحبا"]}
        )
        assert intent is not None

    @pytest.mark.asyncio
    async def test_analyze_fallback_on_llm_error(self):
        """يجب أن يعود بنتيجة حتى لو فشل LLM."""
        from hajeen_platform.brain.cognitive_layer.intent_analyzer import IntentAnalyzer
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(side_effect=Exception("LLM error"))
        analyzer = IntentAnalyzer(llm_manager=llm_mock)
        intent = await analyzer.analyze("أي رسالة")
        assert intent is not None
        assert 0.0 <= intent.confidence <= 1.0

    def test_intent_to_dict(self):
        analyzer, _ = self._make_analyzer()
        loop = asyncio.new_event_loop()
        intent = loop.run_until_complete(analyzer.analyze("test"))
        loop.close()
        d = intent.to_dict()
        assert "intent_id" in d
        assert "category" in d
        assert "confidence" in d
        assert "primary_intent" in d


# ── ContextAnalyzer Tests ───────────────────────────────────────────────────

class TestContextAnalyzer:
    """اختبارات محلل السياق."""

    def _make_analyzer(self):
        from hajeen_platform.brain.cognitive_layer.context_analyzer import ContextAnalyzer

        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='''
{
  "domain": "code",
  "expertise_level": "intermediate",
  "confidence": 0.88,
  "reasoning": "مصطلحات تقنية",
  "complexity": "medium",
  "estimated_tokens": 500,
  "required_capabilities": ["code_generation"],
  "constraints": [],
  "priorities": ["accuracy"],
  "time_sensitivity": "low",
  "recommendations": [],
  "summary": "طلب برمجي"
}''')
        emb_mock = MagicMock()
        emb_mock.embed = AsyncMock(return_value=[0.1, 0.2, 0.3] * 128)

        mem_mock = MagicMock()
        long_term_mock = MagicMock()
        long_term_mock.list_keys = MagicMock(return_value=[])
        mem_mock.get_long_term_memory = MagicMock(return_value=long_term_mock)
        mem_mock.get_conversation = MagicMock(return_value=MagicMock(
            get_window=MagicMock(return_value=[]),
            get_summary_context=MagicMock(return_value=""),
        ))
        mem_mock.semantic = MagicMock(search=MagicMock(return_value=[]))

        return ContextAnalyzer(
            llm_manager=llm_mock,
            embedding_manager=emb_mock,
            memory_fabric=mem_mock,
        )

    def test_init(self):
        analyzer = self._make_analyzer()
        assert analyzer is not None
        assert hasattr(analyzer, "analyze")

    @pytest.mark.asyncio
    async def test_analyze_returns_context_analysis(self):
        analyzer = self._make_analyzer()
        ctx = await analyzer.analyze("كيف أحسّن أداء Python؟", session_id="s1")
        assert ctx is not None
        assert ctx.analysis_id
        assert ctx.session_id == "s1"
        assert isinstance(ctx.relevant_memories, list)
        assert isinstance(ctx.constraints, list)
        assert 0.0 <= ctx.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_memory_retrieval_with_embedding(self):
        """يتحقق أن _retrieve_relevant_memories يستخدم embeddings."""
        from hajeen_platform.brain.cognitive_layer.context_analyzer import ContextAnalyzer

        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='{"domain":"general","expertise_level":"intermediate","confidence":0.7,"reasoning":"","complexity":"simple","estimated_tokens":100,"required_capabilities":[],"constraints":[],"priorities":[],"time_sensitivity":"low","recommendations":[],"summary":""}')
        emb_mock = MagicMock()
        emb_mock.embed = AsyncMock(return_value=[0.5] * 10)

        # ذاكرة بها مدخلات حقيقية
        long_term_mock = MagicMock()
        long_term_mock.list_keys = MagicMock(return_value=["key1", "key2"])
        long_term_mock.recall = MagicMock(return_value={
            "content": "محتوى ذاكرة مهم عن Python",
            "metadata": {},
        })

        mem_mock = MagicMock()
        mem_mock.get_long_term_memory = MagicMock(return_value=long_term_mock)
        mem_mock.get_conversation = MagicMock(return_value=MagicMock(
            get_window=MagicMock(return_value=[]),
            get_summary_context=MagicMock(return_value=""),
        ))
        mem_mock.semantic = MagicMock(search=MagicMock(return_value=[]))

        analyzer = ContextAnalyzer(llm_mock, emb_mock, mem_mock)
        memories = await analyzer._retrieve_relevant_memories("Python code", "s1")
        # يجب أن يُستدعى embed
        assert emb_mock.embed.called

    @pytest.mark.asyncio
    async def test_analyze_with_user_id(self):
        analyzer = self._make_analyzer()
        ctx = await analyzer.analyze("سؤال", session_id="s2", user_id="u1")
        assert ctx is not None

    def test_context_to_dict(self):
        analyzer = self._make_analyzer()
        loop = asyncio.new_event_loop()
        ctx = loop.run_until_complete(analyzer.analyze("test", session_id="s_test"))
        loop.close()
        d = ctx.to_dict()
        assert "analysis_id" in d
        assert "detected_domain" in d
        assert "confidence" in d


# ── ReasoningEngine Tests ───────────────────────────────────────────────────

class TestReasoningEngine:
    """اختبارات محرك الاستدلال."""

    def _make_engine(self):
        from hajeen_platform.brain.cognitive_layer.reasoning_engine import ReasoningEngine

        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='''
{
  "strategy": "chain_of_thought",
  "steps": [
    {"description": "تحليل المشكلة", "reasoning": "...", "conclusion": "...", "confidence": 0.9, "alternatives": []}
  ],
  "missing_information": [],
  "risks": [],
  "solution_options": [
    {
      "title": "الحل الأمثل",
      "description": "استخدام خوارزمية مناسبة",
      "pros": ["سريع"],
      "cons": ["يحتاج ذاكرة"],
      "effort_estimate": "low",
      "time_estimate": "1 hour",
      "risk_level": "low",
      "feasibility_score": 0.9,
      "recommended": true
    }
  ],
  "recommended_solution_index": 0,
  "confidence": 0.88,
  "summary": "الحل موجود وواضح"
}''')
        return ReasoningEngine(llm_manager=llm_mock)

    def test_init(self):
        engine = self._make_engine()
        assert engine is not None
        assert hasattr(engine, "reason")

    @pytest.mark.asyncio
    async def test_reason_returns_result(self):
        engine = self._make_engine()
        result = await engine.reason("كيف أحل مشكلة الفرز؟", context={})
        assert result is not None
        assert result.result_id
        assert isinstance(result.reasoning_steps, list)
        assert isinstance(result.risks, list)
        assert isinstance(result.solution_options, list)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_reason_with_context(self):
        engine = self._make_engine()
        result = await engine.reason(
            "كيف أُحسّن أداء قاعدة بيانات؟",
            context={"domain": "database", "complexity": "complex"},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_reason_recommended_solution(self):
        engine = self._make_engine()
        result = await engine.reason("مشكلة ما", context={})
        if result.solution_options:
            assert result.recommended_solution is not None
            assert hasattr(result.recommended_solution, "title")

    @pytest.mark.asyncio
    async def test_reason_fallback_on_error(self):
        """يجب أن يعود بنتيجة حتى لو فشل LLM."""
        from hajeen_platform.brain.cognitive_layer.reasoning_engine import ReasoningEngine
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(side_effect=Exception("LLM error"))
        engine = ReasoningEngine(llm_manager=llm_mock)
        result = await engine.reason("مشكلة", context={})
        assert result is not None

    def test_reasoning_result_to_dict(self):
        engine = self._make_engine()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(engine.reason("test", context={}))
        loop.close()
        d = result.to_dict()
        assert "result_id" in d
        assert "strategy" in d
        assert "confidence" in d


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
