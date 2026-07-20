"""
اختبارات وحدة و تكامل لمحرك الاستدلال
======================================

Tests for ReasoningEngine with:
- Configuration
- Execution Trace
- Metrics
- Error Recovery
"""

from __future__ import annotations

import asyncio
import pytest
import sys
import os
from typing import Any, Dict, Optional

# Add path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))


# ── Mock LLM Manager ───────────────────────────────────────────────────────────

class MockLLMManager:
    """LLM Manager وهمي للاختبارات."""
    
    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self.responses = responses or {}
        self.call_count = 0
        self.calls = []
    
    async def generate(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """استدعاء وهمي للـ LLM."""
        self.call_count += 1
        self.calls.append({
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        
        # إرجاع استجابة وهمية
        if self.call_count == 1:
            return '''{
  "steps": [
    {
      "step_number": 1,
      "description": "فهم المشكلة",
      "reasoning": "تحليل المدخلات",
      "conclusion": "المشكلة واضحة",
      "confidence": 0.85,
      "alternatives": ["طريقة أخرى"]
    },
    {
      "step_number": 2,
      "description": "تحديد المتغيرات",
      "reasoning": "استخراج المتغيرات الرئيسية",
      "conclusion": "تم تحديد 3 متغيرات",
      "confidence": 0.90,
      "alternatives": []
    }
  ]
}'''
        elif self.call_count == 2:
            return '["المعلومات الناقصة 1", "المعلومات الناقصة 2"]'
        elif self.call_count == 3:
            return '''{
  "risks": [
    {
      "risk_type": "تقنية",
      "description": "مخاطر تقنية محتملة",
      "severity": "medium",
      "probability": 0.4,
      "impact": "تأثير متوسط",
      "mitigation_strategy": "خطة تخفيف"
    }
  ]
}'''
        elif self.call_count == 4:
            return '''{
  "solutions": [
    {
      "title": "الحل الأول",
      "description": "وصف الحل الأول",
      "pros": ["إيجابية 1", "إيجابية 2"],
      "cons": ["سلبية 1"],
      "effort_estimate": "medium",
      "time_estimate": "أسبوع",
      "risk_level": "low",
      "feasibility_score": 0.85
    },
    {
      "title": "الحل الثاني",
      "description": "وصف الحل الثاني",
      "pros": ["إيجابية 1"],
      "cons": ["سلبية 1", "سلبية 2"],
      "effort_estimate": "high",
      "time_estimate": "شهر",
      "risk_level": "medium",
      "feasibility_score": 0.65
    }
  ]
}'''
        
        return '{"steps": []}'


# ── Test Configuration ────────────────────────────────────────────────────────

class TestConfiguration:
    """اختبارات الإعدادات."""
    
    def test_default_config_creation(self):
        """اختبار إنشاء الإعدادات الافتراضية."""
        from brain.config import ReasoningEngineConfig, get_default_config
        
        config = get_default_config()
        
        assert config is not None
        assert config.name == "ReasoningEngine"
        assert config.version == "1.0.0"
        assert config.cache.enabled is True
        assert config.metrics.enabled is True
        assert config.logging.level == "INFO"
    
    def test_config_custom_values(self):
        """اختبار الإعدادات المخصصة."""
        from brain.config import ReasoningEngineConfig, CacheConfig
        
        config = ReasoningEngineConfig(
            name="TestEngine",
            version="2.0.0",
        )
        config.cache = CacheConfig(enabled=False)
        
        assert config.name == "TestEngine"
        assert config.version == "2.0.0"
        assert config.cache.enabled is False
    
    def test_config_serialization(self):
        """اختبار تسلسل الإعدادات."""
        from brain.config import ReasoningEngineConfig
        
        config = ReasoningEngineConfig()
        data = config.model_dump()
        
        assert "name" in data
        assert "version" in data
        assert "cache" in data
        assert "metrics" in data
    
    def test_reasoning_strategy_types(self):
        """اختبار أنواع استراتيجيات الاستدلال."""
        from brain.config import ReasoningStrategyType
        
        assert ReasoningStrategyType.CHAIN_OF_THOUGHT.value == "chain_of_thought"
        assert ReasoningStrategyType.TREE_OF_THOUGHT.value == "tree_of_thought"
        assert ReasoningStrategyType.DECOMPOSITION.value == "decomposition"


# ── Test Execution Trace ──────────────────────────────────────────────────────

class TestExecutionTrace:
    """اختبارات سجل التنفيذ."""
    
    def test_trace_creation(self):
        """اختبار إنشاء تتبع."""
        from brain.execution_trace import ExecutionTrace, TraceLevel
        
        trace = ExecutionTrace(
            trace_id="test-trace-1",
            reasoning_id="test-reasoning-1",
            created_at=1234567890.0,
            problem="مشكلة اختبار",
            strategy="chain_of_thought",
            level=TraceLevel.STANDARD,
        )
        
        assert trace.trace_id == "test-trace-1"
        assert trace.reasoning_id == "test-reasoning-1"
        assert trace.success is True
    
    def test_trace_completion(self):
        """اختبار إكمال التتبع."""
        from brain.execution_trace import ExecutionTrace
        
        trace = ExecutionTrace(
            trace_id="test-trace-1",
            reasoning_id="test-reasoning-1",
            created_at=1234567890.0,
        )
        
        trace.complete(success=True, final_confidence=0.85)
        
        assert trace.success is True
        assert trace.final_confidence == 0.85
        assert trace.completed_at is not None
        assert trace.total_duration_ms is not None
    
    def test_trace_to_dict(self):
        """اختبار تحويل التتبع إلى قاموس."""
        from brain.execution_trace import ExecutionTrace
        
        trace = ExecutionTrace(
            trace_id="test-trace-1",
            reasoning_id="test-reasoning-1",
            created_at=1234567890.0,
        )
        
        data = trace.to_dict()
        
        assert "trace_id" in data
        assert "reasoning_id" in data
        assert "created_at" in data
        assert "events_count" in data
    
    def test_trace_manager(self):
        """اختبار مدير التتبع."""
        from brain.execution_trace import ExecutionTraceManager, TraceLevel
        
        manager = ExecutionTraceManager(
            enabled=True,
            level=TraceLevel.STANDARD,
        )
        
        trace = manager.start_trace(
            reasoning_id="test-1",
            problem="مشكلة اختبار",
            strategy="chain_of_thought",
        )
        
        assert trace is not None
        assert trace.reasoning_id == "test-1"
        
        completed = manager.end_trace("test-1", success=True, final_confidence=0.9)
        assert completed is not None
        assert completed.success is True
    
    def test_trace_statistics(self):
        """اختبار إحصائيات التتبع."""
        from brain.execution_trace import ExecutionTraceManager
        
        manager = ExecutionTraceManager(enabled=True)
        
        # إنشاء بعض التتبعات
        trace = manager.start_trace("r1", "مشكلة 1", "cot")
        manager.end_trace("r1", success=True)
        
        trace = manager.start_trace("r2", "مشكلة 2", "tot")
        manager.end_trace("r2", success=False)
        
        stats = manager.get_statistics()
        
        assert stats["total_traces"] == 2
        assert stats["successful_traces"] == 1
        assert stats["failed_traces"] == 1


# ── Test Metrics ───────────────────────────────────────────────────────────────

class TestMetrics:
    """اختبارات المقاييس."""
    
    def test_metrics_collector_creation(self):
        """اختبار إنشاء جامع المقاييس."""
        from brain.metrics_engine import MetricsCollector
        
        metrics = MetricsCollector(enabled=True, prefix="test")
        
        assert metrics.prefix == "test"
        assert metrics.enabled is True
    
    def test_counter_increment(self):
        """اختبار زيادة العداد."""
        from brain.metrics_engine import MetricsCollector
        
        metrics = MetricsCollector(enabled=True)
        
        metrics.increment("test_counter")
        metrics.increment("test_counter")
        metrics.increment("test_counter", value=5)
        
        assert metrics.get_counter("test_counter") == 7
    
    def test_gauge_set(self):
        """اختبار تعيين Gauge."""
        from brain.metrics_engine import MetricsCollector
        
        metrics = MetricsCollector(enabled=True)
        
        metrics.set_gauge("test_gauge", 42.5)
        metrics.set_gauge("test_gauge", 100.0)
        
        assert metrics.get_gauge("test_gauge") == 100.0
    
    def test_histogram_observation(self):
        """اختبار ملاحظة Histogram."""
        from brain.metrics_engine import MetricsCollector
        
        metrics = MetricsCollector(enabled=True)
        
        metrics.observe_histogram("test_histogram", 10.0)
        metrics.observe_histogram("test_histogram", 20.0)
        metrics.observe_histogram("test_histogram", 30.0)
        
        stats = metrics.get_histogram_stats("test_histogram")
        
        assert stats["count"] == 3
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["mean"] == 20.0
    
    def test_timing_record(self):
        """اختبار تسجيل التوقيت."""
        from brain.metrics_engine import MetricsCollector
        
        metrics = MetricsCollector(enabled=True)
        
        metrics.record_timing("test_operation", 150.0, success=True)
        metrics.record_timing("test_operation", 200.0, success=False)
        
        stats = metrics.get_timing_stats("test_operation")
        
        assert stats["count"] == 2
        assert stats["success_count"] == 1
        assert stats["min_duration_ms"] == 150.0
        assert stats["max_duration_ms"] == 200.0
    
    def test_metrics_summary(self):
        """اختبار ملخص المقاييس."""
        from brain.metrics_engine import MetricsCollector
        
        metrics = MetricsCollector(enabled=True)
        
        metrics.increment("reasoning_total")
        metrics.increment("reasoning_success")
        metrics.increment("cache_hit_total", value=10)
        metrics.increment("cache_miss_total", value=2)
        
        summary = metrics.get_summary()
        
        assert "reasoning" in summary
        assert "cache" in summary
        assert summary["reasoning"]["success_rate"] == 1.0
        assert summary["cache"]["hit_rate"] == 10 / 12


# ── Test Models (Pydantic) ────────────────────────────────────────────────────

class TestPydanticModels:
    """اختبارات نماذج Pydantic."""
    
    def test_reasoning_step_validation(self):
        """اختبار التحقق من خطوة الاستدلال."""
        from brain.cognitive_layer.reasoning_engine import ReasoningStep
        
        step = ReasoningStep(
            step_number=1,
            description="اختبار",
            reasoning="استدلال",
            conclusion="خلاصة",
            confidence=0.8,
            alternatives=["بديل 1"],
        )
        
        assert step.step_number == 1
        assert step.confidence == 0.8
        assert len(step.alternatives) == 1
    
    def test_reasoning_step_invalid_confidence(self):
        """اختبار رفض درجة ثقة غير صالحة."""
        from brain.cognitive_layer.reasoning_engine import ReasoningStep
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            ReasoningStep(
                step_number=1,
                description="اختبار",
                reasoning="استدلال",
                conclusion="خلاصة",
                confidence=1.5,  # غير صالح
            )
    
    def test_solution_option_validation(self):
        """اختبار التحقق من خيار الحل."""
        from brain.cognitive_layer.reasoning_engine import SolutionOption
        
        solution = SolutionOption(
            title="حل اختبار",
            description="وصف الحل",
            pros=["إيجابية 1"],
            cons=["سلبية 1"],
            effort_estimate="low",
            risk_level="medium",
            feasibility_score=0.75,
        )
        
        assert solution.title == "حل اختبار"
        assert solution.effort_estimate == "low"
        assert solution.feasibility_score == 0.75
    
    def test_risk_assessment_validation(self):
        """اختبار التحقق من تقييم المخاطر."""
        from brain.cognitive_layer.reasoning_engine import RiskAssessment
        
        risk = RiskAssessment(
            risk_type="تقنية",
            description="مخاطر تقنية",
            severity="high",
            probability=0.7,
            impact="تأثير كبير",
            mitigation_strategy="استراتيجية",
        )
        
        assert risk.severity == "high"
        assert risk.probability == 0.7
    
    def test_risk_invalid_severity(self):
        """اختبار رفض شدة غير صالحة."""
        from brain.cognitive_layer.reasoning_engine import RiskAssessment
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_type="تقنية",
                description="مخاطر تقنية",
                severity="invalid",  # غير صالح
                probability=0.5,
                impact="تأثير",
                mitigation_strategy="استراتيجية",
            )


# ── Test Reasoning Engine ──────────────────────────────────────────────────────

class TestReasoningEngine:
    """اختبارات محرك الاستدلال."""
    
    @pytest.fixture
    def mock_llm(self):
        """إنشاء LLM وهمي."""
        return MockLLMManager()
    
    @pytest.fixture
    def engine(self, mock_llm):
        """إنشاء محرك استدلال وهمي."""
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        
        return ReasoningEngine(llm_manager=mock_llm)
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, mock_llm):
        """اختبار تهيئة المحرك."""
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        
        engine = ReasoningEngine(llm_manager=mock_llm)
        
        assert engine.llm_manager is mock_llm
        assert engine.config is not None
        assert engine.trace_manager is not None
        assert engine.metrics is not None
    
    @pytest.mark.asyncio
    async def test_basic_reasoning(self, engine, mock_llm):
        """اختبار استدلال أساسي."""
        result = await engine.reason("كيف أبني تطبيق ذكاء اصطناعي؟")
        
        assert result is not None
        assert result.reasoning_id is not None
        assert len(result.reasoning_steps) > 0
        assert result.overall_confidence > 0
        assert mock_llm.call_count > 0
    
    @pytest.mark.asyncio
    async def test_empty_problem_validation(self, engine):
        """اختبار رفض مشكلة فارغة."""
        from brain.cognitive_layer.reasoning_engine import ValidationError
        
        with pytest.raises(ValidationError):
            await engine.reason("")
        
        with pytest.raises(ValidationError):
            await engine.reason("   ")
    
    @pytest.mark.asyncio
    async def test_custom_strategy(self, engine, mock_llm):
        """اختبار استخدام استراتيجية مخصصة."""
        from brain.cognitive_layer.reasoning_engine import ReasoningStrategy
        
        result = await engine.reason(
            "اختبر استراتيجية",
            strategy=ReasoningStrategy.TREE_OF_THOUGHT,
        )
        
        assert result.strategy_used == ReasoningStrategy.TREE_OF_THOUGHT
    
    @pytest.mark.asyncio
    async def test_caching(self, engine, mock_llm):
        """اختبار التخزين المؤقت."""
        problem = "مشكلة للاختبار"
        
        # الاستدلال الأول
        result1 = await engine.reason(problem)
        first_llm_calls = mock_llm.call_count
        
        # الاستدلال الثاني (نفس المشكلة)
        result2 = await engine.reason(problem)
        
        # يجب أن يكون عدد استدعاءات LLM كما هو
        assert mock_llm.call_count == first_llm_calls
        assert result1.reasoning_id == result2.reasoning_id
    
    @pytest.mark.asyncio
    async def test_cache_disabled(self, mock_llm):
        """اختبار تعطيل التخزين المؤقت."""
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        from brain.config import ReasoningEngineConfig, CacheConfig
        
        config = ReasoningEngineConfig()
        config.cache = CacheConfig(enabled=False)
        
        engine = ReasoningEngine(llm_manager=mock_llm, config=config)
        
        problem = "مشكلة للاختبار"
        
        await engine.reason(problem)
        first_calls = mock_llm.call_count
        
        await engine.reason(problem)
        
        # يجب أن يزداد عدد الاستدعاءات
        assert mock_llm.call_count > first_calls
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, engine, mock_llm):
        """اختبار جمع المقاييس."""
        await engine.reason("مشكلة اختبار")
        
        summary = engine.get_metrics_summary()
        
        assert "reasoning" in summary
        assert summary["reasoning"]["total"] > 0
    
    @pytest.mark.asyncio
    async def test_trace_collection(self, engine, mock_llm):
        """اختبار جمع التتبع."""
        await engine.reason("مشكلة اختبار")
        
        stats = engine.get_trace_statistics()
        
        assert "total_traces" in stats
    
    def test_clear_cache(self, engine):
        """اختبار مسح التخزين المؤقت."""
        count = engine.clear_cache()
        
        assert count >= 0
    
    def test_list_reasoning(self, engine):
        """اختبار قائمة الاستدلالات."""
        results = engine.list_reasoning(limit=5)
        
        assert isinstance(results, list)
        assert len(results) <= 5


# ── Test Strategies ───────────────────────────────────────────────────────────

class TestStrategies:
    """اختبارات الاستراتيجيات."""
    
    @pytest.mark.asyncio
    async def test_all_strategies(self):
        """اختبار جميع الاستراتيجيات."""
        from brain.cognitive_layer.reasoning_engine import (
            ReasoningEngine,
            ReasoningStrategy,
        )
        
        mock_llm = MockLLMManager()
        engine = ReasoningEngine(llm_manager=mock_llm)
        
        strategies = [
            ReasoningStrategy.CHAIN_OF_THOUGHT,
            ReasoningStrategy.TREE_OF_THOUGHT,
            ReasoningStrategy.DECOMPOSITION,
            ReasoningStrategy.FIRST_PRINCIPLES,
            ReasoningStrategy.MULTI_PERSPECTIVE,
            ReasoningStrategy.ANALOGY,
        ]
        
        for strategy in strategies:
            result = await engine.reason(
                "اختبر استراتيجية",
                strategy=strategy,
            )
            
            assert result is not None
            assert result.strategy_used == strategy


# ── Test Singleton & Factory ──────────────────────────────────────────────────

class TestSingletonFactory:
    """اختبارات Singleton و Factory."""
    
    def test_get_reasoning_engine_singleton(self):
        """اختبار Singleton."""
        from brain.cognitive_layer.reasoning_engine import (
            get_reasoning_engine,
            reset_reasoning_engine,
        )
        
        reset_reasoning_engine()
        
        engine1 = get_reasoning_engine()
        engine2 = get_reasoning_engine()
        
        # يجب أن يكون نفس الـ instance
        assert engine1 is engine2
    
    def test_create_reasoning_engine_factory(self):
        """اختبار Factory."""
        from brain.cognitive_layer.reasoning_engine import (
            create_reasoning_engine,
            reset_reasoning_engine,
        )
        
        reset_reasoning_engine()
        
        mock_llm = MockLLMManager()
        engine = create_reasoning_engine(mock_llm)
        
        assert engine is not None
        assert engine.llm_manager is mock_llm
    
    def test_reset_engine(self):
        """اختبار إعادة تعيين المحرك."""
        from brain.cognitive_layer.reasoning_engine import (
            get_reasoning_engine,
            reset_reasoning_engine,
        )
        
        reset_reasoning_engine()
        
        engine1 = get_reasoning_engine()
        reset_reasoning_engine()
        engine2 = get_reasoning_engine()
        
        # يجب أن يكونا مختلفين بعد إعادة التعيين
        assert engine1 is not engine2


# ── Test Integration ───────────────────────────────────────────────────────────

class TestIntegration:
    """اختبارات التكامل."""
    
    @pytest.mark.asyncio
    async def test_full_reasoning_pipeline(self):
        """اختبار خط أنابيب الاستدلال الكامل."""
        from brain.cognitive_layer.reasoning_engine import (
            ReasoningEngine,
            ReasoningStrategy,
        )
        from brain.config import ReasoningEngineConfig
        
        mock_llm = MockLLMManager()
        config = ReasoningEngineConfig()
        
        engine = ReasoningEngine(llm_manager=mock_llm, config=config)
        
        result = await engine.reason(
            problem="كيف أحسن من أداء نموذج التعلم الآلي؟",
            context={"domain": "ml", "experience": "متوسط"},
            strategy=ReasoningStrategy.CHAIN_OF_THOUGHT,
        )
        
        # التحقق من النتيجة
        assert result.reasoning_id is not None
        assert len(result.reasoning_steps) > 0
        assert len(result.solution_options) > 0
        assert result.recommended_solution is not None
        assert 0 <= result.overall_confidence <= 1
        assert len(result.reasoning_summary) > 0
        
        # التحقق من التتبع
        assert result.trace_id is not None
        
        # التحقق من المقاييس
        summary = engine.get_metrics_summary()
        assert summary["reasoning"]["total"] > 0
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_reasoning(self):
        """اختبار استدلالات متزامنة."""
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        
        mock_llm = MockLLMManager()
        engine = ReasoningEngine(llm_manager=mock_llm)
        
        problems = [
            "ما هو تعلم الآلة؟",
            "كيف يعمل التعلم العميق؟",
            "ما هي الشبكات العصبية؟",
        ]
        
        # تنفيذ متزامن
        tasks = [engine.reason(p) for p in problems]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for result in results:
            assert result.reasoning_id is not None
            assert result.overall_confidence > 0


# ── Run Tests ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
