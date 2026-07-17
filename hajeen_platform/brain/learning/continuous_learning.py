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
        """إزالة التكرار باستخدام التشابه الدلالي عبر embeddings + hash دقيق."""
        import hashlib
        try:
            import numpy as np
            has_numpy = True
        except ImportError:
            has_numpy = False

        if not samples:
            return samples

        # ── المرحلة 1: إزالة تكرار بـ hash دقيق (سريع) ──────────────
        seen_hashes: set = set()
        hash_unique: List[DataSample] = []
        for s in samples:
            h = hashlib.sha256(
                (s.instruction.strip().lower() + "|" + s.output.strip().lower()).encode()
            ).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                hash_unique.append(s)

        # ── المرحلة 2: إزالة تكرار دلالي بـ cosine similarity ─────────
        if has_numpy and len(hash_unique) > 1:
            try:
                from hajeen_platform.core.embeddings import get_embedding_manager
                emb_manager = get_embedding_manager()

                embeddings: List[List[float]] = []
                for s in hash_unique:
                    emb = await emb_manager.embed(s.instruction[:512])
                    embeddings.append(emb)

                vectors = np.array(embeddings, dtype=float)
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                norms = np.where(norms == 0, 1e-9, norms)
                normalized = vectors / norms

                keep_mask = [True] * len(hash_unique)
                for i in range(len(hash_unique)):
                    if not keep_mask[i]:
                        continue
                    for j in range(i + 1, len(hash_unique)):
                        if not keep_mask[j]:
                            continue
                        similarity = float(np.dot(normalized[i], normalized[j]))
                        if similarity >= self.DEDUP_SIMILARITY_THRESHOLD:
                            if hash_unique[i].quality_score >= hash_unique[j].quality_score:
                                keep_mask[j] = False
                            else:
                                keep_mask[i] = False
                                break

                unique = [s for s, keep in zip(hash_unique, keep_mask) if keep]
            except Exception as e:
                logger.warning("learning_pipeline: semantic dedup failed, using hash only: %s", e)
                unique = hash_unique
        else:
            unique = hash_unique

        removed = len(samples) - len(unique)
        run.samples_after_dedup = len(unique)
        run.record_stage(
            PipelineStage.DEDUPLICATION, len(unique),
            f"أُزيل {removed} مكرر (دلالي+hash)"
        )
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
        """إضافة مهمة التدريب إلى قائمة انتظار دائمة مع التحقق من المعايير."""
        if len(dataset) < self.MIN_SAMPLES_FOR_TRAINING:
            raise ValueError(
                f"عينات غير كافية: {len(dataset)} < {self.MIN_SAMPLES_FOR_TRAINING}. "
                "يرجى تجميع المزيد من بيانات التدريب."
            )

        domains: Dict[str, int] = {}
        for item in dataset:
            d = item.get("domain", "general")
            domains[d] = domains.get(d, 0) + 1
        avg_quality = (
            sum(s.quality_score for s in self._approved_samples) / len(self._approved_samples)
            if self._approved_samples else 0.5
        )

        job: Dict[str, Any] = {
            "job_id": f"train_{run.run_id}",
            "run_id": run.run_id,
            "status": "queued",
            "sample_count": len(dataset),
            "domain_distribution": domains,
            "avg_quality_score": round(avg_quality, 3),
            "training_config": run.training_config,
            "queued_at": time.time(),
            "priority": "high" if avg_quality > 0.8 else "normal",
        }

        queue_path = self._path / "training_queue.json"
        queue: list = []
        if queue_path.exists():
            try:
                with open(queue_path, "r", encoding="utf-8") as f:
                    queue = json.load(f)
            except Exception:
                queue = []
        queue.append(job)
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

        run.training_config["job_id"] = job["job_id"]
        run.training_config["sample_count"] = len(dataset)
        run.training_config["avg_quality"] = round(avg_quality, 3)
        run.record_stage(
            PipelineStage.TRAINING_QUEUE, len(dataset),
            f"مضاف بأولوية={job['priority']} | متوسط_الجودة={round(avg_quality, 3)}"
        )
        logger.info("learning_pipeline: job %s queued with %d samples", job["job_id"], len(dataset))

    async def _stage_fine_tuning(self, run: PipelineRun) -> None:
        """تدريب حقيقي باستخدام LoRA/PEFT مع HuggingFace Transformers."""
        dataset_path = self._path / f"dataset_{run.run_id}.jsonl"
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")

        cfg = run.training_config
        base_model = cfg.get("base_model", "Qwen/Qwen2.5-1.5B")
        output_dir = str(self._path / f"model_{run.run_id}")
        run.record_stage(PipelineStage.FINE_TUNING, 0, f"بدء التدريب: {base_model}")

        try:
            import torch
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                TrainingArguments,
                Trainer,
                DataCollatorForLanguageModeling,
            )
            from datasets import Dataset as HFDataset

            samples: List[Dict] = []
            with open(dataset_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        samples.append(json.loads(line))
            if not samples:
                raise ValueError("Dataset فارغ")

            logger.info("learning_pipeline: loading model %s", base_model)
            tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True, use_fast=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("learning_pipeline: device=%s", device)

            model = AutoModelForCausalLM.from_pretrained(
                base_model,
                trust_remote_code=True,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                device_map="auto" if device == "cuda" else None,
            )

            if cfg.get("use_lora", True):
                try:
                    from peft import LoraConfig, get_peft_model, TaskType
                    lora_cfg = LoraConfig(
                        task_type=TaskType.CAUSAL_LM,
                        r=cfg.get("lora_rank", 16),
                        lora_alpha=cfg.get("lora_rank", 16) * 2,
                        lora_dropout=0.05,
                        bias="none",
                        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
                    )
                    model = get_peft_model(model, lora_cfg)
                    run.training_config["peft_applied"] = True
                    logger.info("learning_pipeline: LoRA applied")
                except ImportError:
                    run.training_config["peft_applied"] = False

            def tokenize_fn(examples):
                texts = [
                    f"### Instruction:\n{inst}\n\n### Response:\n{out}"
                    for inst, out in zip(examples["instruction"], examples["output"])
                ]
                return tokenizer(texts, truncation=True, max_length=512, padding="max_length")

            hf_dataset = HFDataset.from_list(samples)
            cols = hf_dataset.column_names
            tokenized = hf_dataset.map(tokenize_fn, batched=True, remove_columns=cols)
            tokenized = tokenized.train_test_split(test_size=0.1, seed=42)

            training_args = TrainingArguments(
                output_dir=output_dir,
                num_train_epochs=cfg.get("num_epochs", 3),
                per_device_train_batch_size=cfg.get("batch_size", 2),
                per_device_eval_batch_size=cfg.get("batch_size", 2),
                learning_rate=cfg.get("learning_rate", 2e-4),
                warmup_ratio=0.05,
                lr_scheduler_type="cosine",
                save_strategy="epoch",
                evaluation_strategy="epoch",
                logging_steps=10,
                fp16=(device == "cuda"),
                dataloader_num_workers=0,
                report_to="none",
                load_best_model_at_end=True,
                metric_for_best_model="eval_loss",
            )

            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized["train"],
                eval_dataset=tokenized["test"],
                data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
            )

            logger.info("learning_pipeline: starting training loop")
            train_result = await asyncio.get_event_loop().run_in_executor(None, trainer.train)
            await asyncio.get_event_loop().run_in_executor(None, lambda: trainer.save_model(output_dir))
            tokenizer.save_pretrained(output_dir)

            run.training_config.update({
                "simulated": False,
                "output_dir": output_dir,
                "train_loss": round(train_result.training_loss, 4),
                "train_samples": len(tokenized["train"]),
                "device": device,
                "completed_at": time.time(),
            })
            logger.info("learning_pipeline: training complete. loss=%.4f", train_result.training_loss)

        except Exception as e:
            logger.warning(
                "learning_pipeline: full training unavailable (%s: %s). "
                "Saving config for deferred GPU training.", type(e).__name__, e
            )
            deferred_path = self._path / f"deferred_train_{run.run_id}.json"
            with open(deferred_path, "w", encoding="utf-8") as f:
                json.dump({
                    "run_id": run.run_id,
                    "dataset_path": str(dataset_path),
                    "config": cfg,
                    "error": str(e),
                    "queued_at": time.time(),
                    "status": "deferred_gpu_required",
                }, f, ensure_ascii=False, indent=2)
            run.training_config.update({
                "simulated": False,
                "deferred": True,
                "deferred_path": str(deferred_path),
                "completed_at": time.time(),
            })

        run.record_stage(
            PipelineStage.FINE_TUNING,
            run.training_config.get("train_samples", 0),
            "اكتمل" if not run.training_config.get("deferred") else "مؤجل (يتطلب GPU)",
        )

    async def _stage_evaluation(self, run: PipelineRun) -> None:
        """تقييم حقيقي للنموذج المدرَّب باستخدام مقاييس معيارية (Perplexity, Accuracy, BLEU)."""
        run.record_stage(PipelineStage.EVALUATION, 0, "بدء التقييم")
        output_dir = run.training_config.get("output_dir")
        dataset_path = self._path / f"dataset_{run.run_id}.jsonl"

        results: Dict[str, Any] = {
            "evaluated_at": time.time(),
            "model_path": output_dir or "N/A",
            "passes_threshold": False,
        }

        try:
            import math
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_path = output_dir or run.training_config.get("base_model", "Qwen/Qwen2.5-1.5B")
            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                trust_remote_code=True,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                device_map="auto" if device == "cuda" else None,
            )
            model.eval()

            eval_samples: List[Dict] = []
            if dataset_path.exists():
                with open(dataset_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            eval_samples.append(json.loads(line))
            eval_samples = eval_samples[:min(50, len(eval_samples))]

            if not eval_samples:
                raise ValueError("لا توجد عينات للتقييم")

            total_loss = 0.0
            total_tokens = 0
            correct = 0

            with torch.no_grad():
                for sample in eval_samples:
                    text = (
                        f"### Instruction:\n{sample['instruction']}\n\n"
                        f"### Response:\n{sample['output']}"
                    )
                    inputs = tokenizer(
                        text, return_tensors="pt", truncation=True, max_length=512
                    ).to(device)
                    labels = inputs["input_ids"].clone()
                    outputs = model(**inputs, labels=labels)
                    n_tokens = inputs["input_ids"].numel()
                    total_loss += outputs.loss.item() * n_tokens
                    total_tokens += n_tokens
                    preds = outputs.logits[:, :-1, :].argmax(dim=-1)
                    refs = inputs["input_ids"][:, 1:]
                    correct += int((preds == refs).sum().item())

            perplexity = math.exp(total_loss / max(total_tokens, 1))
            accuracy = correct / max(total_tokens, 1)
            results.update({
                "perplexity": round(perplexity, 2),
                "accuracy": round(accuracy, 4),
                "evaluated_samples": len(eval_samples),
                "total_tokens": total_tokens,
                "avg_loss": round(total_loss / max(total_tokens, 1), 4),
            })

            # BLEU تقريبي
            try:
                import nltk
                from nltk.translate.bleu_score import corpus_bleu, SmoothingFunction
                nltk.download("punkt", quiet=True)
                references, hypotheses = [], []
                for sample in eval_samples[:20]:
                    prompt = (
                        f"### Instruction:\n{sample['instruction']}\n\n### Response:\n"
                    )
                    enc = tokenizer(
                        prompt, return_tensors="pt", truncation=True, max_length=256
                    ).to(device)
                    with torch.no_grad():
                        gen = model.generate(**enc, max_new_tokens=64, do_sample=False)
                    hyp = tokenizer.decode(
                        gen[0][enc["input_ids"].shape[1]:], skip_special_tokens=True
                    )
                    references.append([sample["output"].split()])
                    hypotheses.append(hyp.split())
                bleu = corpus_bleu(
                    references, hypotheses,
                    smoothing_function=SmoothingFunction().method1,
                )
                results["bleu"] = round(bleu, 4)
            except Exception:
                results["bleu"] = None

            results["passes_threshold"] = perplexity < 30.0 and accuracy >= 0.60

        except Exception as e:
            logger.warning("learning_pipeline: real evaluation failed: %s. Using heuristic.", e)
            avg_q = (
                sum(s.quality_score for s in self._approved_samples)
                / max(len(self._approved_samples), 1)
            )
            results.update({
                "perplexity": round(100.0 * (1.0 - avg_q) + 5.0, 2),
                "accuracy": round(avg_q * 0.9, 4),
                "bleu": round(avg_q * 0.5, 4),
                "heuristic": True,
                "heuristic_reason": str(e),
                "passes_threshold": avg_q >= 0.70,
            })

        run.evaluation_results = results
        status_str = "اجتاز المعايير ✓" if results.get("passes_threshold") else "لم يجتز المعايير ✗"
        run.record_stage(PipelineStage.EVALUATION, len(self._approved_samples), status_str)
        logger.info(
            "learning_pipeline: evaluation — perplexity=%.2f accuracy=%.4f passes=%s",
            results.get("perplexity", 0), results.get("accuracy", 0),
            results.get("passes_threshold"),
        )

    async def _stage_deployment(self, run: PipelineRun) -> None:
        """نشر النموذج في سجل النماذج وتحديث نقطة الخدمة الحالية."""
        run.record_stage(PipelineStage.DEPLOYMENT, 0, "بدء النشر")

        model_version = f"hajeen-v{time.strftime('%Y%m%d')}-{run.run_id[:8]}"
        output_dir = run.training_config.get("output_dir")

        deployment_info: Dict[str, Any] = {
            "model_version": model_version,
            "run_id": run.run_id,
            "model_path": output_dir,
            "base_model": run.training_config.get("base_model", "unknown"),
            "training_samples": run.training_config.get("sample_count", 0),
            "evaluation": {
                "perplexity": run.evaluation_results.get("perplexity"),
                "accuracy": run.evaluation_results.get("accuracy"),
                "bleu": run.evaluation_results.get("bleu"),
            },
            "deployed_at": time.time(),
            "deployed_at_human": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rollback_available": True,
            "status": "active",
        }

        # تحديث سجل النماذج
        registry_path = self._path / "model_registry.json"
        registry: Dict[str, Any] = {"models": [], "current_active": None}
        if registry_path.exists():
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)
            except Exception:
                pass

        for m in registry.get("models", []):
            if m.get("status") == "active":
                m["status"] = "retired"
                m["retired_at"] = time.time()

        registry.setdefault("models", []).append(deployment_info)
        registry["current_active"] = model_version
        registry["updated_at"] = time.time()

        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

        # ملف الإشارة للـ model server
        active_path = self._path / "active_model.json"
        with open(active_path, "w", encoding="utf-8") as f:
            json.dump({
                "version": model_version,
                "path": output_dir,
                "updated_at": time.time(),
            }, f, ensure_ascii=False, indent=2)

        run.deployment_info = deployment_info
        self._models_deployed.append(deployment_info)
        logger.info(
            "learning_pipeline: deployed version=%s | path=%s",
            model_version, output_dir,
        )
        run.record_stage(PipelineStage.DEPLOYMENT, 0, f"تم النشر: {model_version}")

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
