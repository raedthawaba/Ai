"""
Training Pipeline — منظومة التدريب الكاملة لـ Hajeen Model v1.

تشمل:
- Dataset Builder
- LoRA Fine-Tuning
- Checkpoint Manager
- Metrics Logger
- Evaluation Pipeline
- Experiment Tracking

ملاحظة: التدريب الفعلي يتطلب GPU (CUDA).
        على CPU يمكن تشغيل النموذج في وضع inference فقط.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHECKPOINTS_DIR = Path(__file__).parent / "checkpoints"
LOGS_DIR = Path(__file__).parent / "logs"
EVALUATION_DIR = Path(__file__).parent / "evaluation"


# ─── Experiment Config ────────────────────────────────────────────────────────


@dataclass
class ExperimentConfig:
    """إعداد تجربة التدريب."""
    experiment_id: str = field(default_factory=lambda: f"exp_{int(time.time())}")
    base_model: str = "Qwen/Qwen2.5-1.5B"
    output_name: str = "hajeen-model-v1"
    dataset_path: str = "hajeen_model/data/dataset_train.jsonl"
    eval_dataset_path: str = "hajeen_model/data/dataset_eval.jsonl"

    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"])

    # Training
    num_epochs: int = 3
    batch_size: int = 4
    gradient_accumulation: int = 8
    learning_rate: float = 2e-4
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01

    # Checkpointing
    save_steps: int = 200
    eval_steps: int = 100
    logging_steps: int = 10
    save_total_limit: int = 5

    # Output
    output_dir: str = "hajeen_model/checkpoints"

    def to_dict(self) -> Dict:
        return asdict(self)


# ─── Metrics Logger ───────────────────────────────────────────────────────────


class MetricsLogger:
    """يسجل metrics التدريب والتقييم."""

    def __init__(self, experiment_id: str):
        self.experiment_id = experiment_id
        self._log_path = LOGS_DIR / f"{experiment_id}_metrics.jsonl"
        LOGS_DIR.mkdir(exist_ok=True)
        self._entries: List[Dict] = []

    def log(self, step: int, metrics: Dict, phase: str = "train"):
        entry = {
            "experiment_id": self.experiment_id,
            "step": step,
            "phase": phase,
            "timestamp": time.time(),
            **metrics,
        }
        self._entries.append(entry)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def summary(self) -> Dict:
        if not self._entries:
            return {}
        train = [e for e in self._entries if e.get("phase") == "train"]
        eval_ = [e for e in self._entries if e.get("phase") == "eval"]
        return {
            "total_steps": len(train),
            "final_train_loss": train[-1].get("loss") if train else None,
            "final_eval_loss": eval_[-1].get("eval_loss") if eval_ else None,
            "eval_count": len(eval_),
            "log_path": str(self._log_path),
        }


# ─── Checkpoint Manager ───────────────────────────────────────────────────────


class CheckpointManager:
    """إدارة نقاط الحفظ."""

    def __init__(self, output_dir: str = str(CHECKPOINTS_DIR)):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints: List[Dict] = []

    def save_metadata(self, step: int, metrics: Dict, config: ExperimentConfig) -> str:
        ckpt_dir = self.output_dir / f"checkpoint-{step}"
        ckpt_dir.mkdir(exist_ok=True)
        meta = {
            "step": step,
            "metrics": metrics,
            "config": config.to_dict(),
            "timestamp": time.time(),
            "path": str(ckpt_dir),
        }
        (ckpt_dir / "training_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._checkpoints.append(meta)
        logger.info("Checkpoint saved: step=%d path=%s", step, ckpt_dir)
        return str(ckpt_dir)

    def list_checkpoints(self) -> List[Dict]:
        checkpoints = []
        for d in sorted(self.output_dir.glob("checkpoint-*")):
            meta_file = d / "training_meta.json"
            if meta_file.exists():
                try:
                    checkpoints.append(json.loads(meta_file.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return checkpoints

    def get_best_checkpoint(self) -> Optional[Dict]:
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        with_loss = [c for c in checkpoints if c.get("metrics", {}).get("eval_loss")]
        if with_loss:
            return min(with_loss, key=lambda x: x["metrics"]["eval_loss"])
        return checkpoints[-1]

    def cleanup_old(self, keep: int = 5):
        checkpoints = sorted(self.list_checkpoints(), key=lambda x: x["step"])
        to_delete = checkpoints[:-keep]
        for ckpt in to_delete:
            import shutil
            try:
                shutil.rmtree(ckpt["path"])
                logger.info("Deleted old checkpoint: %s", ckpt["path"])
            except Exception as e:
                logger.warning("Cannot delete %s: %s", ckpt["path"], e)


# ─── Evaluator ────────────────────────────────────────────────────────────────


class ModelEvaluator:
    """تقييم النموذج بعد التدريب."""

    TEST_QUESTIONS_AR = [
        "ما هو الذكاء الاصطناعي؟",
        "ما أهمية تعلم الآلة؟",
        "كيف تعمل الشبكات العصبية؟",
        "ما الفرق بين AI و ML؟",
        "ما تأثير الذكاء الاصطناعي على سوق العمل؟",
    ]
    TEST_QUESTIONS_EN = [
        "What is artificial intelligence?",
        "How does machine learning work?",
        "What are neural networks?",
        "What is deep learning?",
        "How does NLP work?",
    ]

    async def evaluate_with_ollama(self, model_name: str = "qwen2.5:1.5b") -> Dict:
        """تقييم النموذج عبر Ollama."""
        from hajeen_model.hajeen_model_v1 import get_hajeen_model, HajeenRequest, HajeenMessage
        model = get_hajeen_model()
        results = []

        all_questions = self.TEST_QUESTIONS_AR + self.TEST_QUESTIONS_EN
        for q in all_questions:
            t0 = time.perf_counter()
            try:
                request = HajeenRequest(messages=[HajeenMessage("user", q)])
                resp = await model.complete(request)
                latency = (time.perf_counter() - t0) * 1000
                results.append({
                    "question": q,
                    "answer": resp.content[:200],
                    "latency_ms": round(latency, 1),
                    "tokens": resp.total_tokens,
                    "provider": resp.provider,
                    "is_mock": resp.is_mock,
                    "status": "ok",
                })
            except Exception as e:
                results.append({"question": q, "status": "error", "error": str(e)})

        passed = sum(1 for r in results if r.get("status") == "ok")
        avg_latency = sum(r.get("latency_ms", 0) for r in results if r.get("status") == "ok") / max(passed, 1)

        report = {
            "total_questions": len(all_questions),
            "passed": passed,
            "failed": len(all_questions) - passed,
            "pass_rate": round(passed / len(all_questions) * 100, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "results": results,
            "timestamp": time.time(),
        }

        output_path = EVALUATION_DIR / f"eval_{int(time.time())}.json"
        EVALUATION_DIR.mkdir(exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Evaluation saved: %s", output_path)
        return report


# ─── Training Pipeline ────────────────────────────────────────────────────────


class TrainingPipeline:
    """
    Pipeline التدريب الكامل لـ Hajeen Model v1.

    للتدريب الفعلي تحتاج:
    - CUDA GPU بذاكرة 8GB+
    - pip install transformers peft trl accelerate
    - بيانات كافية (1000+ مثال)

    للاختبار بدون GPU: استخدم run_simulation()
    """

    def __init__(self, config: Optional[ExperimentConfig] = None):
        self.config = config or ExperimentConfig()
        self.metrics_logger = MetricsLogger(self.config.experiment_id)
        self.checkpoint_manager = CheckpointManager(self.config.output_dir)
        self.evaluator = ModelEvaluator()
        self._start_time: Optional[float] = None

    def check_requirements(self) -> Dict:
        """فحص متطلبات التدريب."""
        reqs = {
            "python_ok": True,
            "transformers": False,
            "peft": False,
            "trl": False,
            "accelerate": False,
            "torch": False,
            "cuda": False,
            "dataset_exists": Path(self.config.dataset_path).exists(),
            "min_samples": False,
            "gpu_memory_gb": 0,
        }
        for pkg in ["transformers", "peft", "trl", "accelerate"]:
            try:
                __import__(pkg)
                reqs[pkg] = True
            except ImportError:
                pass
        try:
            import torch
            reqs["torch"] = True
            reqs["cuda"] = torch.cuda.is_available()
            if reqs["cuda"]:
                reqs["gpu_memory_gb"] = round(
                    torch.cuda.get_device_properties(0).total_memory / 1e9, 1
                )
        except ImportError:
            pass

        if reqs["dataset_exists"]:
            count = sum(1 for _ in open(self.config.dataset_path, encoding="utf-8"))
            reqs["dataset_count"] = count
            reqs["min_samples"] = count >= 100

        can_train = (
            reqs["transformers"] and reqs["peft"] and reqs["torch"]
            and reqs["cuda"] and reqs["min_samples"]
        )
        reqs["can_train"] = can_train
        reqs["blockers"] = []
        if not reqs["torch"]:
            reqs["blockers"].append("torch غير مثبت")
        if not reqs["cuda"]:
            reqs["blockers"].append("لا يوجد GPU — التدريب يتطلب CUDA")
        if not reqs["min_samples"]:
            reqs["blockers"].append("البيانات غير كافية (< 100 مثال)")
        if not reqs["peft"]:
            reqs["blockers"].append("pip install peft trl مطلوب")

        return reqs

    def run_simulation(self) -> Dict:
        """
        محاكاة التدريب بدون GPU.
        لاختبار Pipeline بدون موارد فعلية.
        """
        logger.info("=== بدء محاكاة التدريب (Simulation Mode) ===")
        self._start_time = time.time()

        import random as rnd
        total_steps = 30
        train_loss = 3.0

        for step in range(1, total_steps + 1):
            train_loss = max(0.5, train_loss * (1 - rnd.uniform(0.02, 0.05)))
            if step % self.config.logging_steps == 0:
                metrics = {
                    "loss": round(train_loss, 4),
                    "learning_rate": self.config.learning_rate * (1 - step / total_steps),
                    "epoch": round(step / total_steps * self.config.num_epochs, 2),
                }
                self.metrics_logger.log(step, metrics, "train")

            if step % self.config.eval_steps == 0 or step == total_steps:
                eval_loss = train_loss + rnd.uniform(0.1, 0.3)
                self.metrics_logger.log(step, {"eval_loss": round(eval_loss, 4)}, "eval")
                self.checkpoint_manager.save_metadata(
                    step,
                    {"train_loss": round(train_loss, 4), "eval_loss": round(eval_loss, 4)},
                    self.config,
                )

        elapsed = time.time() - self._start_time
        summary = self.metrics_logger.summary()

        return {
            "mode": "simulation",
            "experiment_id": self.config.experiment_id,
            "total_steps": total_steps,
            "elapsed_sec": round(elapsed, 2),
            "final_train_loss": summary.get("final_train_loss"),
            "final_eval_loss": summary.get("final_eval_loss"),
            "checkpoints": self.checkpoint_manager.list_checkpoints(),
            "note": "هذه محاكاة — للتدريب الحقيقي تحتاج GPU + بيانات كافية",
        }

    def run_training(self) -> Dict:
        """
        التدريب الفعلي عبر HuggingFace + PEFT (LoRA).
        يتطلب GPU + المكتبات المناسبة.
        """
        reqs = self.check_requirements()
        if not reqs["can_train"]:
            logger.error("Training requirements not met: %s", reqs["blockers"])
            return {
                "status": "cannot_train",
                "blockers": reqs["blockers"],
                "requirements": reqs,
                "alternative": "استخدم run_simulation() للاختبار أو شغّل على GPU خارجي",
            }

        logger.info("=== بدء التدريب الفعلي ===")
        self._start_time = time.time()

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
            from peft import LoraConfig, get_peft_model, TaskType
            from trl import SFTTrainer
            from datasets import load_dataset

            logger.info("Loading tokenizer: %s", self.config.base_model)
            tokenizer = AutoTokenizer.from_pretrained(self.config.base_model, use_fast=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            logger.info("Loading base model: %s", self.config.base_model)
            import torch
            model = AutoModelForCausalLM.from_pretrained(
                self.config.base_model,
                torch_dtype=torch.float16,
                device_map="auto",
            )

            lora_cfg = LoraConfig(
                r=self.config.lora_r,
                lora_alpha=self.config.lora_alpha,
                target_modules=self.config.target_modules,
                lora_dropout=self.config.lora_dropout,
                bias="none",
                task_type=TaskType.CAUSAL_LM,
            )
            model = get_peft_model(model, lora_cfg)
            model.print_trainable_parameters()

            dataset = load_dataset("json", data_files={
                "train": self.config.dataset_path,
                "eval": self.config.eval_dataset_path,
            })

            args = TrainingArguments(
                output_dir=self.config.output_dir,
                num_train_epochs=self.config.num_epochs,
                per_device_train_batch_size=self.config.batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation,
                learning_rate=self.config.learning_rate,
                warmup_ratio=self.config.warmup_ratio,
                weight_decay=self.config.weight_decay,
                fp16=True,
                logging_steps=self.config.logging_steps,
                eval_steps=self.config.eval_steps,
                save_steps=self.config.save_steps,
                save_total_limit=self.config.save_total_limit,
                load_best_model_at_end=True,
                metric_for_best_model="eval_loss",
                evaluation_strategy="steps",
                report_to=[],
                seed=42,
            )

            def formatting_func(example):
                if "instruction" in example:
                    inp = example.get("input", "")
                    text = f"### Instruction:\n{example['instruction']}"
                    if inp:
                        text += f"\n\n### Input:\n{inp}"
                    text += f"\n\n### Response:\n{example['output']}"
                    return text
                return example.get("text", "")

            trainer = SFTTrainer(
                model=model,
                tokenizer=tokenizer,
                train_dataset=dataset["train"],
                eval_dataset=dataset["eval"],
                args=args,
                formatting_func=formatting_func,
                max_seq_length=self.config.max_seq_length,
            )

            logger.info("Training started...")
            train_result = trainer.train()
            elapsed = time.time() - self._start_time

            output_path = Path(self.config.output_dir) / "final"
            trainer.save_model(str(output_path))
            tokenizer.save_pretrained(str(output_path))

            return {
                "status": "success",
                "experiment_id": self.config.experiment_id,
                "output_dir": str(output_path),
                "elapsed_sec": round(elapsed, 2),
                "train_result": {
                    "global_step": train_result.global_step,
                    "training_loss": round(train_result.training_loss, 4),
                },
                "metrics_log": str(self.metrics_logger._log_path),
            }

        except Exception as e:
            logger.error("Training failed: %s", e, exc_info=True)
            return {"status": "error", "error": str(e)}
