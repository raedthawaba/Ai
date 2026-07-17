"""
Integration Tests — Learning Pipeline End-to-End (Phase 11)
===========================================================
يختبر تدفق الـ pipeline الكامل من البيانات الخام حتى النشر.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest

from hajeen_platform.brain.learning.continuous_learning import (
    ContinuousLearningPipeline,
    PipelineStatus,
    PipelineStage,
)


def make_rich_samples(n: int = 60) -> list:
    return [
        {
            "instruction": f"اشرح مفهوم الذكاء الاصطناعي رقم {i} بالتفصيل",
            "output": f"الذكاء الاصطناعي رقم {i} هو فرع من علوم الحاسوب يهتم ببناء أنظمة قادرة على محاكاة الذكاء البشري وتنفيذ المهام المعقدة بكفاءة عالية.",
            "domain": "ai_concepts",
            "source_model": "gpt-4o",
            "quality_score": 0.85,
        }
        for i in range(n)
    ]


class TestPipelineEndToEnd:
    """اختبار تشغيل الـ pipeline كاملاً."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_all_stages(self, tmp_path):
        """يتحقق من أن جميع المراحل تُنفَّذ بالترتيب الصحيح."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = make_rich_samples(60)
        run = await p.run(raw)

        # يجب أن يكتمل (أو يُنشر أو يُتراجع عنه بناءً على التقييم)
        assert run.status in (
            PipelineStatus.COMPLETED,
            PipelineStatus.ROLLED_BACK,
            PipelineStatus.WAITING_APPROVAL,
        )
        assert run.samples_collected == 60
        assert run.samples_after_cleaning > 0

        # التحقق من أن جميع المراحل سُجِّلت في history
        stages_executed = {entry["stage"] for entry in run.stage_history}
        assert PipelineStage.COLLECTION in stages_executed
        assert PipelineStage.CLEANING in stages_executed
        assert PipelineStage.DEDUPLICATION in stages_executed
        assert PipelineStage.QUALITY_VALIDATION in stages_executed

    @pytest.mark.asyncio
    async def test_pipeline_rejects_insufficient_samples(self, tmp_path):
        """يتحقق من رفض عينات أقل من الحد الأدنى."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = make_rich_samples(5)  # أقل من 50
        run = await p.run(raw)
        assert run.status == PipelineStatus.FAILED
        assert run.error is not None

    @pytest.mark.asyncio
    async def test_dataset_file_created(self, tmp_path):
        """يتحقق من إنشاء ملف JSONL للبيانات."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = make_rich_samples(60)
        run = await p.run(raw)

        ds_files = list(Path(tmp_path).glob("dataset_*.jsonl"))
        assert len(ds_files) >= 1
        with open(ds_files[0], "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) > 0
        assert "instruction" in lines[0]
        assert "output" in lines[0]

    @pytest.mark.asyncio
    async def test_training_queue_file_created(self, tmp_path):
        """يتحقق من إنشاء ملف قائمة الانتظار."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = make_rich_samples(60)
        await p.run(raw)

        queue_path = Path(tmp_path) / "training_queue.json"
        assert queue_path.exists()
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
        assert len(queue) >= 1

    @pytest.mark.asyncio
    async def test_run_saved_to_disk(self, tmp_path):
        """يتحقق من حفظ بيانات الـ run على القرص."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        raw = make_rich_samples(60)
        run = await p.run(raw)

        run_file = Path(tmp_path) / f"run_{run.run_id}.json"
        assert run_file.exists()
        with open(run_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["run_id"] == run.run_id

    @pytest.mark.asyncio
    async def test_get_stats_after_run(self, tmp_path):
        """يتحقق من تحديث الإحصائيات بعد الـ run."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        await p.run(make_rich_samples(60))
        stats = p.get_stats()
        assert stats["total_runs"] == 1
        assert stats["completed"] >= 0

    @pytest.mark.asyncio
    async def test_human_approval_flow(self, tmp_path):
        """يتحقق من توقف الـ pipeline عند تفعيل Human Approval."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        p._require_human_approval = True
        raw = make_rich_samples(60)
        run = await p.run(raw)
        assert run.status == PipelineStatus.WAITING_APPROVAL
        assert len(p._pending_approval) > 0

        # الموافقة
        approved_count = await p.approve_pending()
        assert approved_count > 0
        assert len(p._pending_approval) == 0

    @pytest.mark.asyncio
    async def test_multiple_runs_independent(self, tmp_path):
        """يتحقق من استقلالية الـ runs المتعددة."""
        p = ContinuousLearningPipeline(storage_path=str(tmp_path))
        run1 = await p.run(make_rich_samples(60))
        run2 = await p.run(make_rich_samples(60))
        assert run1.run_id != run2.run_id
        assert p.get_stats()["total_runs"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
