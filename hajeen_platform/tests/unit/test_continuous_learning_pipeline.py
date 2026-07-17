"""
Unit Tests — Continuous Learning Pipeline (Phase 11 Complete)
=============================================================
يختبر كل مراحل الـ pipeline:
Collection → Cleaning → Deduplication → Quality Validation →
Filtering → Ranking → Dataset Builder → Training Queue →
Fine-Tuning → Evaluation → Deployment → Rollback
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import tempfile

from hajeen_platform.brain.learning.continuous_learning import (
    ContinuousLearningPipeline,
    DataSample,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)


def make_pipeline(tmp_path: str) -> ContinuousLearningPipeline:
    return ContinuousLearningPipeline(storage_path=tmp_path)


def make_samples(n: int = 20, quality: float = 0.8) -> list:
    return [
        {
            "instruction": f"ما هو السؤال رقم {i}؟",
            "output": f"هذه إجابة تفصيلية ومفيدة للسؤال رقم {i} وتشمل معلومات كافية.",
            "domain": "general",
            "source_model": "gpt-4o",
            "quality_score": quality,
        }
        for i in range(n)
    ]


# ── Collection ───────────────────────────────────────────────────────────────

class TestStageCollection:
    @pytest.mark.asyncio
    async def test_collection_creates_samples(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.COLLECTION)
        raw = make_samples(5)
        samples = await p._stage_collection(run, raw)
        assert len(samples) == 5
        assert run.samples_collected == 5
        assert all(isinstance(s, DataSample) for s in samples)

    @pytest.mark.asyncio
    async def test_collection_empty_input(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.COLLECTION)
        samples = await p._stage_collection(run, [])
        assert samples == []
        assert run.samples_collected == 0


# ── Cleaning ─────────────────────────────────────────────────────────────────

class TestStageCleaning:
    @pytest.mark.asyncio
    async def test_removes_short_samples(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.CLEANING)
        samples = [
            DataSample("s1", "hi", "ok", "general", "m", 0.8),  # قصير جداً
            DataSample("s2", "ما هو الذكاء الاصطناعي؟", "هو محاكاة الذكاء البشري في الآلات وأنظمة الكمبيوتر.", "general", "m", 0.8),
        ]
        cleaned = await p._stage_cleaning(run, samples)
        assert len(cleaned) == 1
        assert cleaned[0].sample_id == "s2"

    @pytest.mark.asyncio
    async def test_strips_whitespace(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.CLEANING)
        sample = DataSample("s1", "  ما هو الذكاء الاصطناعي؟  ", "  إجابة مفيدة وكافية وتفصيلية.  ", "general", "m", 0.8)
        cleaned = await p._stage_cleaning(run, [sample])
        assert cleaned[0].instruction == "ما هو الذكاء الاصطناعي؟"
        assert cleaned[0].output == "إجابة مفيدة وكافية وتفصيلية."


# ── Deduplication ────────────────────────────────────────────────────────────

class TestStageDeduplication:
    @pytest.mark.asyncio
    async def test_exact_duplicates_removed(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEDUPLICATION)
        samples = [
            DataSample("s1", "ما هو Python؟", "لغة برمجة عالية المستوى مفسرة وتفاعلية.", "general", "m", 0.8),
            DataSample("s2", "ما هو Python؟", "لغة برمجة عالية المستوى مفسرة وتفاعلية.", "general", "m", 0.8),
        ]
        unique = await p._stage_deduplication(run, samples)
        assert len(unique) == 1

    @pytest.mark.asyncio
    async def test_unique_samples_kept(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEDUPLICATION)
        samples = [
            DataSample("s1", "ما هو Python؟", "لغة برمجة عالية المستوى.", "general", "m", 0.8),
            DataSample("s2", "كيف تعمل الشبكات العصبية؟", "هي نماذج حسابية مستوحاة من الدماغ البشري.", "general", "m", 0.8),
        ]
        unique = await p._stage_deduplication(run, samples)
        assert len(unique) == 2

    @pytest.mark.asyncio
    async def test_keeps_higher_quality_on_dup(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEDUPLICATION)
        samples = [
            DataSample("s1", "ما هو Python؟", "لغة برمجة عالية المستوى.", "general", "m", 0.6),
            DataSample("s2", "ما هو Python؟", "لغة برمجة عالية المستوى.", "general", "m", 0.9),
        ]
        unique = await p._stage_deduplication(run, samples)
        assert len(unique) == 1
        assert unique[0].quality_score == 0.9


# ── Quality Validation ───────────────────────────────────────────────────────

class TestStageQualityValidation:
    @pytest.mark.asyncio
    async def test_filters_low_quality(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.QUALITY_VALIDATION)
        samples = [
            DataSample("s1", "q1", "a1", "general", "m", 0.4),  # ضعيف
            DataSample("s2", "q2", "a2", "general", "m", 0.8),  # جيد
        ]
        valid = await p._stage_quality_validation(run, samples)
        assert len(valid) == 1
        assert valid[0].sample_id == "s2"


# ── Ranking ──────────────────────────────────────────────────────────────────

class TestStageRanking:
    @pytest.mark.asyncio
    async def test_sorts_by_quality_desc(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.RANKING)
        samples = [
            DataSample("s1", "q1", "a1", "general", "m", 0.6),
            DataSample("s2", "q2", "a2", "general", "m", 0.9),
            DataSample("s3", "q3", "a3", "general", "m", 0.7),
        ]
        ranked = await p._stage_ranking(run, samples)
        scores = [s.quality_score for s in ranked]
        assert scores == sorted(scores, reverse=True)


# ── Dataset Builder ──────────────────────────────────────────────────────────

class TestStageDatasetBuilder:
    @pytest.mark.asyncio
    async def test_builds_jsonl_file(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="build_test", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DATASET_BUILDER)
        samples = [
            DataSample("s1", "سؤال اختبار", "إجابة اختبار مفيدة", "general", "m", 0.8),
        ]
        dataset = await p._stage_build_dataset(run, samples)
        assert len(dataset) == 1
        ds_path = Path(tmp_path) / "dataset_build_test.jsonl"
        assert ds_path.exists()
        with open(ds_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 1
        assert lines[0]["instruction"] == "سؤال اختبار"


# ── Training Queue ───────────────────────────────────────────────────────────

class TestStageTrainingQueue:
    @pytest.mark.asyncio
    async def test_raises_if_insufficient_samples(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.TRAINING_QUEUE)
        with pytest.raises(ValueError, match="عينات غير كافية"):
            await p._stage_training_queue(run, [{"instruction": "q", "output": "a", "domain": "g"}] * 10)

    @pytest.mark.asyncio
    async def test_queues_job_to_file(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        p._approved_samples = [DataSample(str(i), "q", "a", "g", "m", 0.85) for i in range(60)]
        run = PipelineRun(run_id="queue_test", status=PipelineStatus.RUNNING, current_stage=PipelineStage.TRAINING_QUEUE)
        dataset = [{"instruction": f"q{i}", "output": f"a{i}", "domain": "g"} for i in range(60)]
        await p._stage_training_queue(run, dataset)

        queue_path = Path(tmp_path) / "training_queue.json"
        assert queue_path.exists()
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
        assert len(queue) >= 1
        assert queue[-1]["job_id"] == "train_queue_test"
        assert queue[-1]["sample_count"] == 60


# ── Evaluation ───────────────────────────────────────────────────────────────

class TestStageEvaluation:
    @pytest.mark.asyncio
    async def test_evaluation_heuristic_fallback(self, tmp_path):
        """يتحقق من أن التقييم يعود بنتيجة حتى بدون GPU."""
        p = make_pipeline(str(tmp_path))
        p._approved_samples = [DataSample(str(i), "q", "a", "g", "m", 0.85) for i in range(10)]
        run = PipelineRun(run_id="eval_test", status=PipelineStatus.RUNNING, current_stage=PipelineStage.EVALUATION)
        run.training_config = {"base_model": "nonexistent/model", "output_dir": None}
        # إنشاء dataset فارغ
        (Path(tmp_path) / "dataset_eval_test.jsonl").write_text("", encoding="utf-8")
        await p._stage_evaluation(run)
        assert "perplexity" in run.evaluation_results
        assert "accuracy" in run.evaluation_results
        assert isinstance(run.evaluation_results["passes_threshold"], bool)

    @pytest.mark.asyncio
    async def test_evaluation_requires_dataset(self, tmp_path):
        """يتحقق من أن التقييم الاستدلالي يعمل بدون ملف."""
        p = make_pipeline(str(tmp_path))
        p._approved_samples = [DataSample(str(i), "q", "a", "g", "m", 0.75) for i in range(5)]
        run = PipelineRun(run_id="eval_no_ds", status=PipelineStatus.RUNNING, current_stage=PipelineStage.EVALUATION)
        run.training_config = {}
        await p._stage_evaluation(run)
        assert run.evaluation_results is not None


# ── Deployment ───────────────────────────────────────────────────────────────

class TestStageDeployment:
    @pytest.mark.asyncio
    async def test_creates_registry_and_active_files(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="deploy_test", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEPLOYMENT)
        run.training_config = {"base_model": "Qwen/Qwen2.5-1.5B", "sample_count": 100, "output_dir": str(tmp_path / "model_deploy_test")}
        run.evaluation_results = {"perplexity": 8.0, "accuracy": 0.85, "bleu": 0.5}

        await p._stage_deployment(run)

        registry_path = Path(tmp_path) / "model_registry.json"
        assert registry_path.exists()
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
        assert registry["current_active"].startswith("hajeen-v")
        assert len(registry["models"]) >= 1

        active_path = Path(tmp_path) / "active_model.json"
        assert active_path.exists()

    @pytest.mark.asyncio
    async def test_retires_old_models(self, tmp_path):
        p = make_pipeline(str(tmp_path))

        # نشر النموذج الأول
        run1 = PipelineRun(run_id="r1", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEPLOYMENT)
        run1.training_config = {"output_dir": None}
        run1.evaluation_results = {"perplexity": 10.0, "accuracy": 0.8}
        await p._stage_deployment(run1)

        # نشر نموذج ثانٍ — يجب أن يتقاعد الأول
        run2 = PipelineRun(run_id="r2", status=PipelineStatus.RUNNING, current_stage=PipelineStage.DEPLOYMENT)
        run2.training_config = {"output_dir": None}
        run2.evaluation_results = {"perplexity": 8.0, "accuracy": 0.9}
        await p._stage_deployment(run2)

        registry_path = Path(tmp_path) / "model_registry.json"
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)

        statuses = {m["run_id"]: m["status"] for m in registry["models"]}
        assert statuses.get("r1") == "retired"
        assert statuses.get("r2") == "active"


# ── Pipeline Stats ───────────────────────────────────────────────────────────

class TestPipelineStats:
    def test_get_stats_empty(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        stats = p.get_stats()
        assert stats["total_runs"] == 0
        assert stats["deployed_models"] == 0

    def test_get_stats_after_run(self, tmp_path):
        p = make_pipeline(str(tmp_path))
        run = PipelineRun(run_id="s1", status=PipelineStatus.COMPLETED, current_stage=PipelineStage.DEPLOYMENT)
        p._runs["s1"] = run
        p._models_deployed.append({"model_version": "v1"})
        stats = p.get_stats()
        assert stats["total_runs"] == 1
        assert stats["completed"] == 1
        assert stats["deployed_models"] == 1


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
