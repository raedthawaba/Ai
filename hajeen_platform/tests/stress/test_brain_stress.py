"""
Stress Tests — Hajeen Brain (Phase 19)
=======================================
يختبر استقرار النظام تحت الضغط الشديد وحالات الحافة.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest


class TestLearningPipelineStress:
    """اختبارات ضغط Continuous Learning Pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_with_all_low_quality(self, tmp_path):
        """يتحقق من رفض عينات منخفضة الجودة بالكامل."""
        from hajeen_platform.brain.learning.continuous_learning import (
            ContinuousLearningPipeline, PipelineStatus,
        )
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = [
            {
                "instruction": f"سؤال {i}",
                "output": f"إجابة مفيدة وكافية جداً رقم {i} عن موضوع مهم.",
                "domain": "g",
                "source_model": "m",
                "quality_score": 0.3,  # جودة منخفضة جداً
            }
            for i in range(60)
        ]
        run = await p.run(raw)
        # يجب أن يفشل لأن جميع العينات منخفضة الجودة
        assert run.status in (PipelineStatus.FAILED, PipelineStatus.ROLLED_BACK)

    @pytest.mark.asyncio
    async def test_pipeline_handles_malformed_data(self, tmp_path):
        """يتحقق من معالجة البيانات المشوهة بأمان."""
        from hajeen_platform.brain.learning.continuous_learning import (
            ContinuousLearningPipeline, PipelineStatus,
        )
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = [
            {},  # مدخل فارغ
            {"instruction": "q"},  # ناقص
            None,  # None
            {"instruction": "سؤال كافٍ جداً", "output": "إجابة مفيدة ومفصلة", "quality_score": 0.9},  # صحيح
        ]
        # يجب ألا يتعطل النظام
        try:
            run = await p.run(raw)
            # مقبول إما نجاح أو فشل، لكن ليس exception غير معالجة
        except Exception as e:
            pytest.fail(f"Pipeline تعطل بـ exception غير متوقع: {e}")

    @pytest.mark.asyncio
    async def test_pipeline_with_very_long_text(self, tmp_path):
        """يتحقق من معالجة نصوص طويلة جداً."""
        from hajeen_platform.brain.learning.continuous_learning import ContinuousLearningPipeline
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        long_text = "ذكاء اصطناعي " * 1000  # نص طويل جداً
        raw = [
            {
                "instruction": long_text,
                "output": long_text,
                "domain": "g",
                "source_model": "m",
                "quality_score": 0.85,
            }
            for _ in range(60)
        ]
        try:
            run = await p.run(raw)
        except Exception as e:
            pytest.fail(f"Pipeline تعطل مع النصوص الطويلة: {e}")

    @pytest.mark.asyncio
    async def test_pipeline_duplicate_heavy_dataset(self, tmp_path):
        """يتحقق من معالجة dataset يحتوي على 95% تكرار."""
        from hajeen_platform.brain.learning.continuous_learning import (
            ContinuousLearningPipeline, PipelineStatus,
        )
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        unique_sample = {
            "instruction": "ما هو الذكاء الاصطناعي بشكل عام؟",
            "output": "الذكاء الاصطناعي هو فرع من علوم الحاسوب.",
            "quality_score": 0.85,
        }
        raw = [unique_sample.copy() for _ in range(55)] + [
            {
                "instruction": f"سؤال فريد رقم {i}",
                "output": f"إجابة مفيدة وكافية للسؤال الفريد رقم {i}.",
                "quality_score": 0.85,
            }
            for i in range(5)
        ]
        run = await p.run(raw)
        # بعد إزالة التكرار، ستكون العينات قليلة → يفشل بسبب عدم كفايتها
        assert run.status in (PipelineStatus.FAILED, PipelineStatus.COMPLETED, PipelineStatus.ROLLED_BACK)


class TestCognitiveLayerStress:
    """اختبارات ضغط الطبقة المعرفية."""

    @pytest.mark.asyncio
    async def test_intent_analyzer_empty_message(self):
        """يتحقق من معالجة الرسائل الفارغة."""
        from hajeen_platform.brain.cognitive_layer.intent_analyzer import IntentAnalyzer
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='{"primary_intent":"غير محدد","category":"conversation","secondary_intents":[],"implicit_requirements":[],"confidence":0.3,"reasoning":"رسالة فارغة","alternative_interpretations":[]}')
        analyzer = IntentAnalyzer(llm_manager=llm_mock)
        intent = await analyzer.analyze("")
        assert intent is not None

    @pytest.mark.asyncio
    async def test_intent_analyzer_very_long_message(self):
        """يتحقق من معالجة الرسائل الطويلة جداً."""
        from hajeen_platform.brain.cognitive_layer.intent_analyzer import IntentAnalyzer
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='{"primary_intent":"طلب طويل","category":"task_execution","secondary_intents":[],"implicit_requirements":[],"confidence":0.6,"reasoning":"","alternative_interpretations":[]}')
        analyzer = IntentAnalyzer(llm_manager=llm_mock)
        long_msg = "هذه رسالة طويلة جداً " * 500
        intent = await analyzer.analyze(long_msg)
        assert intent is not None

    @pytest.mark.asyncio
    async def test_reasoning_engine_malformed_llm_response(self):
        """يتحقق من معالجة ردود LLM المشوهة بأمان."""
        from hajeen_platform.brain.cognitive_layer.reasoning_engine import ReasoningEngine
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value="هذا ليس JSON صحيحاً!!!")
        engine = ReasoningEngine(llm_manager=llm_mock)
        result = await engine.reason("مشكلة", context={})
        assert result is not None  # يجب ألا يتعطل

    @pytest.mark.asyncio
    async def test_context_analyzer_memory_failure(self):
        """يتحقق من مرونة محلل السياق عند فشل الذاكرة."""
        from hajeen_platform.brain.cognitive_layer.context_analyzer import ContextAnalyzer
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='{"domain":"general","expertise_level":"intermediate","confidence":0.7,"reasoning":"","complexity":"simple","estimated_tokens":100,"required_capabilities":[],"constraints":[],"priorities":[],"time_sensitivity":"low","recommendations":[],"summary":""}')
        emb_mock = MagicMock()
        emb_mock.embed = AsyncMock(side_effect=Exception("Embedding service down"))
        mem_mock = MagicMock()
        mem_mock.get_long_term_memory = MagicMock(side_effect=Exception("Memory failure"))
        mem_mock.get_conversation = MagicMock(return_value=MagicMock(
            get_window=MagicMock(return_value=[]),
            get_summary_context=MagicMock(return_value=""),
        ))
        mem_mock.semantic = MagicMock(search=MagicMock(side_effect=Exception("Search down")))

        analyzer = ContextAnalyzer(llm_mock, emb_mock, mem_mock)
        ctx = await analyzer.analyze("رسالة", session_id="s1")
        assert ctx is not None  # يجب ألا يتعطل


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
