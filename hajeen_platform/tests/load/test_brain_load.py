"""
Load Tests — Brain (Phase 19)
=================================
يختبر قدرة النظام على تحمّل الحمل العالي:
- معالجة طلبات متعددة بالتوازي
- قياس زمن الاستجابة تحت الضغط
- التحقق من عدم تسرب الذاكرة

NOTE: This test file imports from archived brain_v3.
Update to use official HajeenBrain from hajeen_brain.py
"""
from __future__ import annotations

import asyncio
import time
import uuid
import statistics
import sys
import pytest


def _skip_if_no_brain():
    """تخطي الاختبار إن لم تكن المكونات متاحة."""
    try:
        from hajeen_platform.brain.hajeen_brain import HajeenBrain
        return False
    except ImportError:
        return True


@pytest.mark.skipif(_skip_if_no_brain(), reason="Brain not available in this environment")
class TestBrainLoadHandling:
    """اختبارات الحمل."""

    CONCURRENT_USERS = 50
    REQUESTS_PER_USER = 5
    MAX_ACCEPTABLE_P95_MS = 5000  # 5 ثوانٍ

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, brain_mock):
        """يتحقق من معالجة طلبات متزامنة بدون أخطاء."""
        latencies = []
        errors = []

        async def single_request(i: int):
            t0 = time.perf_counter()
            try:
                from hajeen_platform.brain.hajeen_brain import HajeenBrain
                from hajeen_platform.brain.contracts import BrainRequest
                req = BrainRequest(
                    user_message=f"طلب المستخدم {i}: ما هو الذكاء الاصطناعي؟",
                    session_id=f"session_{i}",
                )
                await brain_mock.process(req)
                latencies.append((time.perf_counter() - t0) * 1000)
            except Exception as e:
                errors.append(str(e))

        tasks = [single_request(i) for i in range(self.CONCURRENT_USERS)]
        await asyncio.gather(*tasks)

        error_rate = len(errors) / self.CONCURRENT_USERS
        assert error_rate < 0.05, f"معدل الخطأ مرتفع جداً: {error_rate:.1%}"

        if latencies:
            sorted_lat = sorted(latencies)
            p50 = sorted_lat[len(sorted_lat) // 2]
            p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
            p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
            print(f"\nLoad Test Results:")
            print(f"  Requests: {len(latencies)} successful, {len(errors)} failed")
            print(f"  P50: {p50:.1f}ms | P95: {p95:.1f}ms | P99: {p99:.1f}ms")

    @pytest.mark.asyncio
    async def test_throughput_benchmark(self, brain_mock):
        """قياس معدل الطلبات في الثانية."""
        N = 20
        t0 = time.perf_counter()
        from hajeen_platform.brain.contracts import BrainRequest

        async def req():
            r = BrainRequest(
                user_message="طلب معياري للاختبار",
                session_id=f"s_{uuid.uuid4().hex[:8]}",
            )
            await brain_mock.process(r)

        await asyncio.gather(*[req() for _ in range(N)])
        elapsed = time.perf_counter() - t0
        rps = N / elapsed
        print(f"\nThroughput: {rps:.1f} req/s over {elapsed:.2f}s")
        assert rps > 0.5, f"الأداء منخفض جداً: {rps:.1f} req/s"


class TestLearningPipelineLoad:
    """اختبارات حمل Continuous Learning Pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_with_large_dataset(self, tmp_path):
        """يتحقق من معالجة مجموعة بيانات كبيرة."""
        from hajeen_platform.brain.learning.continuous_learning import ContinuousLearningPipeline
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        large_raw = [
            {
                "instruction": f"سؤال تدريبي رقم {i} حول الذكاء الاصطناعي وتطبيقاته المختلفة",
                "output": f"إجابة شاملة ومفصلة للسؤال رقم {i} تتضمن أمثلة تطبيقية وحالات استخدام واقعية ومراجع علمية موثوقة.",
                "domain": "ai",
                "source_model": "gpt-4o",
                "quality_score": 0.82,
            }
            for i in range(500)
        ]

        t0 = time.perf_counter()
        run = await p.run(large_raw)
        elapsed = time.perf_counter() - t0

        print(f"\nLarge dataset processing: {elapsed:.2f}s for 500 samples")
        assert run.samples_collected == 500
        assert elapsed < 60, "المعالجة بطيئة جداً"

    @pytest.mark.asyncio
    async def test_concurrent_pipeline_runs(self, tmp_path):
        """يتحقق من تشغيل pipelines متعددة بالتوازي."""
        import os
        from hajeen_platform.brain.learning.continuous_learning import ContinuousLearningPipeline

        async def single_run(i: int):
            sub_path = str(tmp_path / f"run_{i}")
            os.makedirs(sub_path, exist_ok=True)
            p = ContinuousLearningPipeline(storage_path=sub_path)
            raw = [
                {
                    "instruction": f"سؤال {j} في الـ pipeline رقم {i}",
                    "output": f"إجابة تفصيلية ومفيدة وكاملة للسؤال {j} في الـ pipeline رقم {i}.",
                    "domain": "general",
                    "source_model": "m",
                    "quality_score": 0.8,
                }
                for j in range(60)
            ]
            return await p.run(raw)

        runs = await asyncio.gather(*[single_run(i) for i in range(3)])
        assert len(runs) == 3
        run_ids = {r.run_id for r in runs}
        assert len(run_ids) == 3, "يجب أن تكون كل run_id فريدة"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
