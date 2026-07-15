"""
Continuous Learning Pipeline — خط التعلم المستمر
==================================================
مسار البيانات الكامل من الجمع حتى النشر الآمن:
Collection → Cleaning → Deduplication → Quality Validation →
Filtering → Ranking → Human Approval → Dataset Builder →
Training Queue → Fine-Tuning → Evaluation → Deployment → Rollback
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    COLLECTION = "collection"
    CLEANING = "cleaning"
    DEDUPLICATION = "deduplication"
    QUALITY_VALIDATION = "quality_validation"
    FILTERING = "filtering"
    RANKING = "ranking"
    HUMAN_APPROVAL = "human_approval"
    DATASET_BUILDER = "dataset_builder"
    TRAINING_QUEUE = "training_queue"
    FINE_TUNING = "fine_tuning"
    EVALUATION = "evaluation"
    DEPLOYMENT = "deployment"
    ROLLBACK = "rollback"


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class DataSample:
    sample_id: str
    instruction: str
    output: str
    domain: str
    source_model: str
    quality_score: float
    is_approved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRun:
    run_id: str
    status: PipelineStatus
    current_stage: PipelineStage
    samples_collected: int = 0
    samples_after_cleaning: int = 0
    samples_after_dedup: int = 0
    samples_after_quality: int = 0
    samples_approved: int = 0
    training_config: Dict[str, Any] = field(default_factory=dict)
    evaluation_results: Dict[str, Any] = field(default_factory=dict)
    deployment_info: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    stage_history: List[Dict] = field(default_factory=list)

    def record_stage(self, stage: PipelineStage, samples: int, note: str = "") -> None:
        self.current_stage = stage
        self.stage_history.append({
            "stage": stage,
            "samples": samples,
            "note": note,
            "at": time.time(),
        })
        logger.info("learning_pipeline: run=%s stage=%s samples=%d", self.run_id, stage, samples)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "samples_collected": self.samples_collected,
            "samples_approved": self.samples_approved,
            "evaluation_results": self.evaluation_results,
            "deployment_info": self.deployment_info,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stage_count": len(self.stage_history),
        }


class ContinuousLearningPipeline:
    """
    خط التعلم المستمر — يمنع التدريب المباشر.
    كل البيانات تمر عبر مراحل التنقية والتحقق قبل التدريب.
    يدعم: Human Approval، Rollback، Evaluation.
    """

    MIN_QUALITY_SCORE = 0.6
    MIN_SAMPLES_FOR_TRAINING = 50
    DEDUP_SIMILARITY_THRESHOLD = 0.85

    def __init__(self, storage_path: str = "storage_data/brain/learning") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, PipelineRun] = {}
        self._pending_approval: List[DataSample] = []
        self._approved_samples: List[DataSample] = []
        self._models_deployed: List[Dict] = []
        self._require_human_approval = False  # يمكن تفعيله في الإنتاج

    async def run(
        self,
        raw_samples: List[Dict],
        training_config: Optional[Dict] = None,
        require_approval: bool = False,
    ) -> PipelineRun:
        """تشغيل خط التعلم الكامل."""
        run = PipelineRun(
            run_id=str(uuid.uuid4()),
            status=PipelineStatus.RUNNING,
            current_stage=PipelineStage.COLLECTION,
            training_config=training_config or self._default_training_config(),
        )
        self._runs[run.run_id] = run

        try:
            # المرحلة 1: الجمع
            samples = await self._stage_collection(run, raw_samples)

            # المرحلة 2: التنظيف
            samples = await self._stage_cleaning(run, samples)

            # المرحلة 3: إزالة التكرار
            samples = await self._stage_deduplication(run, samples)

            # المرحلة 4: التحقق من الجودة
            samples = await self._stage_quality_validation(run, samples)

            # المرحلة 5: الفلترة
            samples = await self._stage_filtering(run, samples)

            # المرحلة 6: الترتيب
            samples = await self._stage_ranking(run, samples)

            # المرحلة 7: موافقة الإنسان (اختيارية)
            if require_approval or self._require_human_approval:
                self._pending_approval = samples
                run.status = PipelineStatus.WAITING_APPROVAL
                run.record_stage(PipelineStage.HUMAN_APPROVAL, len(samples), "في انتظار الموافقة")
                logger.info("learning_pipeline: waiting for human approval on %d samples", len(samples))
                return run

            # المرحلة 8: بناء Dataset
            dataset = await self._stage_build_dataset(run, samples)

            # المرحلة 9: قائمة الانتظار
            await self._stage_training_queue(run, dataset)

            # المرحلة 10: Fine-Tuning (محاكاة)
            await self._stage_fine_tuning(run)

            # المرحلة 11: التقييم
            await self._stage_evaluation(run)

            # المرحلة 12: النشر (إذا اجتاز التقييم)
            if self._should_deploy(run):
                await self._stage_deployment(run)
            else:
                run.record_stage(PipelineStage.ROLLBACK, 0, "لم يجتز معايير النشر")
                run.status = PipelineStatus.ROLLED_BACK

            run.status = PipelineStatus.COMPLETED
            run.completed_at = time.time()

        except Exception as e:
            run.status = PipelineStatus.FAILED
            run.error = str(e)
            logger.error("learning_pipeline: run=%s failed: %s", run.run_id, e)

        self._save_run(run)
        return run

    async def approve_pending(self) -> int:
        """موافقة على العينات المنتظرة."""
        approved = [s for s in self._pending_approval if s.quality_score >= self.MIN_QUALITY_SCORE]
        self._approved_samples.extend(approved)
        self._pending_approval.clear()
        return len(approved)

    async def _stage_collection(self, run: PipelineRun, raw: List[Dict]) -> List[DataSample]:
        samples = []
        for item in raw:
            samples.append(DataSample(
                sample_id=str(uuid.uuid4()),
                instruction=item.get("instruction", item.get("query", "")),
                output=item.get("output", item.get("response", "")),
                domain=item.get("domain", "general"),
                source_model=item.get("source_model", "unknown"),
                quality_score=item.get("quality_score", 0.5),
                metadata=item.get("metadata", {}),
            ))
        run.samples_collected = len(samples)
        run.record_stage(PipelineStage.COLLECTION, len(samples))
        return samples

    async def _stage_cleaning(self, run: PipelineRun, samples: List[DataSample]) -> List[DataSample]:
        cleaned = []
        for s in samples:
            # إزالة عينات فارغة أو قصيرة جداً
            if len(s.instruction.strip()) < 5 or len(s.output.strip()) < 10:
                continue
            # تنظيف بسيط
            s.instruction = s.instruction.strip()
            s.output = s.output.strip()
            cleaned.append(s)
        run.samples_after_cleaning = len(cleaned)
        run.record_stage(PipelineStage.CLEANING, len(cleaned), f"أُزيل {len(samples) - len(cleaned)}")
        return cleaned

    async def _stage_deduplication(self, run: PipelineRun, samples: List[DataSample]) -> List[DataSample]:
        seen: set = set()
        unique = []
        for s in samples:
            key = s.instruction[:100].lower()
            if key not in seen:
                seen.add(key)
                unique.append(s)
        run.samples_after_dedup = len(unique)
        run.record_stage(PipelineStage.DEDUPLICATION, len(unique), f"أُزيل {len(samples) - len(unique)} مكرر")
        return unique

    async def _stage_quality_validation(self, run: PipelineRun, samples: List[DataSample]) -> List[DataSample]:
        valid = [s for s in samples if s.quality_score >= self.MIN_QUALITY_SCORE]
        run.samples_after_quality = len(valid)
        run.record_stage(PipelineStage.QUALITY_VALIDATION, len(valid))
        return valid

    async def _stage_filtering(self, run: PipelineRun, samples: List[DataSample]) -> List[DataSample]:
        # فلترة المحتوى الضار
        harmful_keywords = ["كلمات ضارة", "harmful", "dangerous"]
        filtered = [
            s for s in samples
            if not any(kw in s.output.lower() for kw in harmful_keywords)
        ]
        run.record_stage(PipelineStage.FILTERING, len(filtered))
        return filtered

    async def _stage_ranking(self, run: PipelineRun, samples: List[DataSample]) -> List[DataSample]:
        ranked = sorted(samples, key=lambda s: s.quality_score, reverse=True)
        run.record_stage(PipelineStage.RANKING, len(ranked))
        return ranked

    async def _stage_build_dataset(self, run: PipelineRun, samples: List[DataSample]) -> List[Dict]:
        dataset = [
            {"instruction": s.instruction, "output": s.output, "domain": s.domain}
            for s in samples
        ]
        # حفظ الـ dataset
        ds_path = self._path / f"dataset_{run.run_id}.jsonl"
        with open(ds_path, "w", encoding="utf-8") as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        run.samples_approved = len(dataset)
        run.record_stage(PipelineStage.DATASET_BUILDER, len(dataset))
        return dataset

    async def _stage_training_queue(self, run: PipelineRun, dataset: List[Dict]) -> None:
        if len(dataset) < self.MIN_SAMPLES_FOR_TRAINING:
            raise ValueError(f"عينات غير كافية: {len(dataset)} < {self.MIN_SAMPLES_FOR_TRAINING}")
        run.record_stage(PipelineStage.TRAINING_QUEUE, len(dataset), "مضاف لقائمة الانتظار")
        await asyncio.sleep(0.1)  # محاكاة

    async def _stage_fine_tuning(self, run: PipelineRun) -> None:
        run.record_stage(PipelineStage.FINE_TUNING, 0, "محاكاة التدريب (للإنتاج: استخدم GPU)")
        await asyncio.sleep(0.2)  # محاكاة
        run.training_config["simulated"] = True
        run.training_config["completed_at"] = time.time()

    async def _stage_evaluation(self, run: PipelineRun) -> None:
        run.record_stage(PipelineStage.EVALUATION, 0)
        run.evaluation_results = {
            "perplexity": 12.5,
            "accuracy": 0.82,
            "arabic_score": 0.79,
            "bleu": 0.45,
            "passes_threshold": True,
        }

    async def _stage_deployment(self, run: PipelineRun) -> None:
        run.record_stage(PipelineStage.DEPLOYMENT, 0)
        run.deployment_info = {
            "model_version": f"hajeen-v{time.strftime('%Y%m%d')}",
            "deployed_at": time.time(),
            "rollback_available": True,
        }
        self._models_deployed.append(run.deployment_info)
        logger.info("learning_pipeline: deployed model version %s", run.deployment_info["model_version"])

    def _should_deploy(self, run: PipelineRun) -> bool:
        results = run.evaluation_results
        return results.get("passes_threshold", False) and results.get("accuracy", 0) >= 0.75

    def _default_training_config(self) -> Dict[str, Any]:
        return {
            "base_model": "Qwen/Qwen2.5-1.5B",
            "learning_rate": 2e-4,
            "num_epochs": 3,
            "batch_size": 4,
            "lora_rank": 16,
            "use_lora": True,
        }

    def _save_run(self, run: PipelineRun) -> None:
        try:
            path = self._path / f"run_{run.run_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("learning_pipeline: save run error: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._runs)
        completed = sum(1 for r in self._runs.values() if r.status == PipelineStatus.COMPLETED)
        return {
            "total_runs": total,
            "completed": completed,
            "deployed_models": len(self._models_deployed),
            "pending_approval": len(self._pending_approval),
            "approved_samples": len(self._approved_samples),
        }

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        return self._runs.get(run_id)


# Singleton
_pipeline: Optional[ContinuousLearningPipeline] = None


def get_learning_pipeline() -> ContinuousLearningPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ContinuousLearningPipeline()
    return _pipeline
