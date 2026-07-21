"""
Benchmark Tests — Core Components (Phase 19)
============================================
يقيس أداء المكونات الرئيسية ويضع حداً أدنى مقبولاً للأداء.
"""
from __future__ import annotations

import asyncio
import statistics
import time
import uuid
from typing import List
from unittest.mock import AsyncMock, MagicMock
import pytest


def _time_async(coro_factory, n: int = 10) -> List[float]:
    """تشغيل coroutine بشكل متزامن وقياس الأوقات."""
    loop = asyncio.new_event_loop()
    latencies = []
    try:
        for _ in range(n):
            t0 = time.perf_counter()
            loop.run_until_complete(coro_factory())
            latencies.append((time.perf_counter() - t0) * 1000)
    finally:
        loop.close()
    return latencies


class TestIntentAnalyzerBenchmark:
    ITERATIONS = 20
    MAX_ACCEPTABLE_AVG_MS = 500  # بحد أقصى 500ms متوسطاً

    def test_analyze_latency(self):
        from hajeen_platform.brain.cognitive_layer.intent_analyzer import IntentAnalyzer
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='{"primary_intent":"test","category":"conversation","secondary_intents":[],"implicit_requirements":[],"confidence":0.8,"reasoning":"","alternative_interpretations":[]}')
        analyzer = IntentAnalyzer(llm_manager=llm_mock)

        latencies = _time_async(
            lambda: analyzer.analyze("ما هو الذكاء الاصطناعي؟"),
            self.ITERATIONS
        )

        avg_ms = statistics.mean(latencies)
        p95_ms = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"\n[IntentAnalyzer] avg={avg_ms:.1f}ms p95={p95_ms:.1f}ms over {self.ITERATIONS} runs")
        assert avg_ms < self.MAX_ACCEPTABLE_AVG_MS, f"متوسط بطيء: {avg_ms:.1f}ms"


class TestReasoningEngineBenchmark:
    ITERATIONS = 10
    MAX_ACCEPTABLE_AVG_MS = 1000

    def test_reason_latency(self):
        from hajeen_platform.brain.cognitive_layer.reasoning_engine import ReasoningEngine
        llm_mock = MagicMock()
        llm_mock.generate = AsyncMock(return_value='{"strategy":"chain_of_thought","steps":[],"missing_information":[],"risks":[],"solution_options":[],"recommended_solution_index":null,"confidence":0.7,"summary":""}')
        engine = ReasoningEngine(llm_manager=llm_mock)

        latencies = _time_async(
            lambda: engine.reason("مشكلة بسيطة", context={}),
            self.ITERATIONS
        )

        avg_ms = statistics.mean(latencies)
        print(f"\n[ReasoningEngine] avg={avg_ms:.1f}ms over {self.ITERATIONS} runs")
        assert avg_ms < self.MAX_ACCEPTABLE_AVG_MS, f"متوسط بطيء: {avg_ms:.1f}ms"


class TestContinuousLearningBenchmark:
    def test_deduplication_speed(self, tmp_path):
        """يقيس سرعة إزالة التكرار على مجموعة كبيرة."""
        from hajeen_platform.brain.learning.continuous_learning import (
            ContinuousLearningPipeline, DataSample, PipelineRun, PipelineStatus, PipelineStage,
        )
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        samples = [
            DataSample(
                str(i), f"سؤال فريد رقم {i} عن موضوع مختلف",
                f"إجابة كافية للسؤال رقم {i} تحتوي على معلومات مفيدة.",
                "general", "m", 0.8,
            )
            for i in range(200)
        ]
        run = PipelineRun(run_id="bench1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEDUPLICATION)

        loop = asyncio.new_event_loop()
        t0 = time.perf_counter()
        result = loop.run_until_complete(p._stage_deduplication(run, samples))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        loop.close()

        print(f"\n[Deduplication] {len(samples)} samples → {len(result)} unique in {elapsed_ms:.1f}ms")
        assert elapsed_ms < 10_000, f"إزالة التكرار بطيئة جداً: {elapsed_ms:.1f}ms"
        assert len(result) > 0

    def test_cleaning_speed(self, tmp_path):
        """يقيس سرعة مرحلة التنظيف."""
        from hajeen_platform.brain.learning.continuous_learning import (
            ContinuousLearningPipeline, DataSample, PipelineRun, PipelineStatus, PipelineStage,
        )
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        samples = [
            DataSample(str(i), f"  سؤال {i}  ", f"  إجابة مفيدة وكافية رقم {i}  ", "g", "m", 0.8)
            for i in range(1000)
        ]
        run = PipelineRun(run_id="bench2", status=PipelineStatus.RUNNING, current_stage=PipelineStage.CLEANING)

        loop = asyncio.new_event_loop()
        t0 = time.perf_counter()
        loop.run_until_complete(p._stage_cleaning(run, samples))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        loop.close()

        print(f"\n[Cleaning] 1000 samples in {elapsed_ms:.1f}ms")
        assert elapsed_ms < 1000, f"التنظيف بطيء: {elapsed_ms:.1f}ms"


class TestDecisionEngineBenchmark:
    ITERATIONS = 20

    def test_decision_speed(self, tmp_path):
        """يقيس سرعة اتخاذ القرار."""
        from hajeen_platform.brain.decision_engine import DecisionEngineV2, DecisionContext, DecisionType

        engine = DecisionEngineV2()
        
        loop = asyncio.new_event_loop()
        latencies = []
        for _ in range(self.ITERATIONS):
            context = DecisionContext(
                request_id=f"bench-{_}",
                user_message="اختبار الأداء",
                session_id="bench",
                task_count=5,
                available_models=["gpt-4o", "claude-3", "gemini"],
            )
            t0 = time.perf_counter()
            loop.run_until_complete(engine.decide(context, DecisionType.MODEL_SELECTION))
            latencies.append((time.perf_counter() - t0) * 1000)
        loop.close()

        avg_ms = statistics.mean(latencies)
        print(f"\n[DecisionEngineV2] avg={avg_ms:.2f}ms over {len(latencies)} decisions")
        assert avg_ms < 100, f"اتخاذ القرار بطيء: {avg_ms:.2f}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
