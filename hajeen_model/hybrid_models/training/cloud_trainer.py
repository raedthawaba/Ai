"""
cloud_trainer.py — Cloud-Aware Training Pipeline
نظام تدريب سحابي مع دعم HuggingFace، Resume Training، وCheckpoint Saving تلقائي
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


class TextDataset(Dataset):
    """Dataset بسيط للنصوص المرمّزة."""

    def __init__(self, token_ids: List[List[int]], max_seq_len: int = 512):
        self.samples = [ids[:max_seq_len] for ids in token_ids if ids]
        self.max_seq_len = max_seq_len

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        ids = self.samples[idx]
        x = torch.tensor(ids[:-1], dtype=torch.long)
        y = torch.tensor(ids[1:], dtype=torch.long)
        return {"input_ids": x, "labels": y}


def collate_fn(batch: List[Dict[str, torch.Tensor]], pad_id: int = 0) -> Dict[str, torch.Tensor]:
    """دمج دفعات بطول متغير."""
    max_len = max(b["input_ids"].size(0) for b in batch)
    input_ids = torch.zeros(len(batch), max_len, dtype=torch.long)
    labels = torch.full((len(batch), max_len), -100, dtype=torch.long)
    for i, b in enumerate(batch):
        L = b["input_ids"].size(0)
        input_ids[i, :L] = b["input_ids"]
        labels[i, :L] = b["labels"]
    return {"input_ids": input_ids, "labels": labels}


class CloudTrainer:
    """
    نظام التدريب السحابي لـ Hajeen Foundation Model.

    الميزات:
    - تحميل datasets مباشرة من HuggingFace
    - حفظ checkpoints تلقائياً
    - رفع checkpoints أثناء التدريب
    - استكمال التدريب عند الانقطاع (Resume Training)
    - رفع logs تلقائياً
    """

    def __init__(
        self,
        model: nn.Module,
        tokenizer: Any,
        config: Optional[Dict] = None,
        use_hf_cloud: bool = True,
        resume_from_step: Optional[int] = None,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config or self._default_config()
        self.use_hf_cloud = use_hf_cloud
        self.resume_from_step = resume_from_step

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"🖥️  Device: {self.device}")

        self.model.to(self.device)
        self.global_step = resume_from_step or 0
        self.best_loss = float("inf")

        self.checkpoint_dir = Path(
            self.config.get("checkpoint_dir", "./checkpoints")
        )
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.training_log: List[Dict] = []
        self._cloud_sync = None

        if use_hf_cloud:
            self._init_cloud_sync()

    def _default_config(self) -> Dict:
        return {
            "learning_rate": 3e-4,
            "batch_size": 4,
            "gradient_accumulation_steps": 8,
            "max_steps": 100_000,
            "warmup_steps": 1_000,
            "save_every_steps": 500,
            "upload_every_steps": 1_000,
            "log_every_steps": 50,
            "max_seq_len": 512,
            "max_grad_norm": 1.0,
            "weight_decay": 0.01,
            "checkpoint_dir": "./checkpoints",
            "training_output_dir": "./training_output",
        }

    def _init_cloud_sync(self) -> None:
        """تهيئة CloudSync."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
            from cloud.cloud_sync import CloudSync
            self._cloud_sync = CloudSync(sync_interval=300, auto_sync=True)
            self._cloud_sync.start_auto_sync()
            logger.info("✅ Cloud sync مفعّل")
        except Exception as e:
            logger.warning(f"⚠️  لم يتم تفعيل cloud sync: {e}")
            self._cloud_sync = None

    def load_dataset_from_hub(
        self,
        dataset_name: Optional[str] = None,
        split: str = "train",
        text_field: str = "text",
        num_samples: Optional[int] = None,
    ) -> TextDataset:
        """
        تحميل dataset من HuggingFace وتحويله إلى TextDataset.
        """
        from datasets import load_dataset

        dataset_name = dataset_name or os.getenv(
            "HF_DATASET_REPO", "Raedthawaba/hajeen-datasets"
        )
        logger.info(f"⬇️  تحميل dataset: {dataset_name} [{split}]")

        try:
            hf_token = os.getenv("HF_TOKEN")
            ds = load_dataset(
                dataset_name,
                split=split,
                streaming=False,
                token=hf_token,
            )
            if num_samples:
                ds = ds.select(range(min(num_samples, len(ds))))
        except Exception as e:
            logger.warning(f"⚠️  فشل تحميل {dataset_name}: {e} — استخدام بيانات وهمية")
            return self._create_dummy_dataset()

        logger.info(f"🔤 ترميز {len(ds)} نص...")
        token_ids = []
        for record in ds:
            text = record.get(text_field, "") or ""
            if not text.strip():
                continue
            encoded = self.tokenizer.encode(
                text,
                truncation=True,
                max_length=self.config["max_seq_len"] + 1,
            )
            if len(encoded) > 10:
                token_ids.append(encoded)

        logger.info(f"✅ Dataset جاهز: {len(token_ids)} نص مُرمَّز")
        return TextDataset(
            token_ids=token_ids,
            max_seq_len=self.config["max_seq_len"],
        )

    def _create_dummy_dataset(self) -> TextDataset:
        """إنشاء dataset وهمي للاختبار."""
        logger.warning("⚠️  استخدام dataset وهمي للاختبار")
        dummy_texts = [
            "الذكاء الاصطناعي يغير العالم بشكل متسارع.",
            "Hajeen is a powerful Arabic language model.",
            "يتعلم النموذج من البيانات الضخمة ويولد نصاً عربياً.",
        ] * 100
        token_ids = []
        for text in dummy_texts:
            ids = self.tokenizer.encode(text)
            token_ids.append(ids + [0])
        return TextDataset(token_ids=token_ids, max_seq_len=self.config["max_seq_len"])

    def resume_from_checkpoint(self) -> None:
        """استكمال التدريب من آخر checkpoint."""
        if not self.resume_from_step:
            return

        checkpoint_path = self.checkpoint_dir / f"step_{self.resume_from_step}"
        if checkpoint_path.exists():
            logger.info(f"🔄 استكمال التدريب من step={self.resume_from_step}")
            self._load_checkpoint(checkpoint_path)
        else:
            logger.warning(f"⚠️  Checkpoint step={self.resume_from_step} غير موجود محلياً")
            if self.use_hf_cloud and self._cloud_sync:
                try:
                    logger.info("⬇️  محاولة تحميل checkpoint من HuggingFace...")
                    from cloud.model_manager import ModelManager
                    mm = ModelManager()
                    mm.download_checkpoint(step=self.resume_from_step, local_dir=str(self.checkpoint_dir / "resumed"))
                except Exception as e:
                    logger.error(f"❌ فشل تحميل checkpoint: {e}")

    def _load_checkpoint(self, checkpoint_path: Path) -> None:
        """تحميل checkpoint من القرص."""
        model_path = checkpoint_path / "model.pt"
        optimizer_path = checkpoint_path / "optimizer.pt"

        if model_path.exists():
            state = torch.load(str(model_path), map_location=self.device)
            self.model.load_state_dict(state["model_state_dict"])
            self.global_step = state.get("step", self.global_step)
            self.best_loss = state.get("best_loss", self.best_loss)
            logger.info(f"✅ تم تحميل النموذج من {model_path}")

    def _save_checkpoint(self, optimizer: AdamW, loss: float) -> Path:
        """حفظ checkpoint محلياً."""
        step = self.global_step
        checkpoint_path = self.checkpoint_dir / f"step_{step}"
        checkpoint_path.mkdir(parents=True, exist_ok=True)

        torch.save({
            "step": step,
            "model_state_dict": self.model.state_dict(),
            "loss": loss,
            "best_loss": self.best_loss,
        }, str(checkpoint_path / "model.pt"))

        torch.save({
            "optimizer_state_dict": optimizer.state_dict(),
        }, str(checkpoint_path / "optimizer.pt"))

        metrics = {"loss": loss, "step": step, "timestamp": datetime.now().isoformat()}
        (checkpoint_path / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )

        logger.info(f"💾 Checkpoint محفوظ: {checkpoint_path}")
        return checkpoint_path

    def _upload_checkpoint(self, checkpoint_path: Path, loss: float) -> None:
        """رفع checkpoint إلى HuggingFace."""
        if not self.use_hf_cloud or not self._cloud_sync:
            return
        try:
            self._cloud_sync.sync_checkpoint_with_report(
                checkpoint_path=str(checkpoint_path),
                step=self.global_step,
                metrics={"loss": loss, "perplexity": 2 ** loss},
            )
            logger.info(f"⬆️  Checkpoint مرفوع إلى HuggingFace: step={self.global_step}")
        except Exception as e:
            logger.error(f"❌ فشل رفع checkpoint: {e}")

    def train(
        self,
        dataset: Optional[TextDataset] = None,
        dataset_name: Optional[str] = None,
        num_samples: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        تنفيذ حلقة التدريب الكاملة.
        """
        if dataset is None:
            dataset = self.load_dataset_from_hub(
                dataset_name=dataset_name,
                num_samples=num_samples,
            )

        if self.resume_from_step:
            self.resume_from_checkpoint()

        dataloader = DataLoader(
            dataset,
            batch_size=self.config["batch_size"],
            shuffle=True,
            collate_fn=lambda b: collate_fn(b),
            num_workers=0,
        )

        optimizer = AdamW(
            self.model.parameters(),
            lr=self.config["learning_rate"],
            weight_decay=self.config["weight_decay"],
        )
        scheduler = CosineAnnealingLR(
            optimizer, T_max=self.config["max_steps"]
        )

        logger.info(f"🚀 بدء التدريب — {len(dataset)} عينة، {self.config['max_steps']} step")
        logger.info(f"   Learning Rate: {self.config['learning_rate']}")
        logger.info(f"   Batch Size: {self.config['batch_size']}")
        logger.info(f"   Device: {self.device}")

        self.model.train()
        accumulated_loss = 0.0
        start_time = time.time()

        for epoch in range(1, 9999):
            for batch in dataloader:
                if self.global_step >= self.config["max_steps"]:
                    break

                input_ids = batch["input_ids"].to(self.device)
                labels = batch["labels"].to(self.device)

                outputs = self.model(input_ids=input_ids, labels=labels)
                loss = outputs["loss"] if isinstance(outputs, dict) else outputs[0]
                loss = loss / self.config["gradient_accumulation_steps"]

                loss.backward()
                accumulated_loss += loss.item()

                if (self.global_step + 1) % self.config["gradient_accumulation_steps"] == 0:
                    torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(), self.config["max_grad_norm"]
                    )
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()

                self.global_step += 1

                if self.global_step % self.config["log_every_steps"] == 0:
                    avg_loss = accumulated_loss / max(self.config["log_every_steps"], 1)
                    elapsed = time.time() - start_time
                    perplexity = min(2 ** avg_loss, 1e6)
                    lr = scheduler.get_last_lr()[0]

                    log_entry = {
                        "step": self.global_step,
                        "epoch": epoch,
                        "loss": round(avg_loss, 4),
                        "perplexity": round(perplexity, 2),
                        "learning_rate": lr,
                        "elapsed_seconds": round(elapsed, 1),
                    }
                    self.training_log.append(log_entry)
                    logger.info(
                        f"📈 Step {self.global_step:>6} | "
                        f"Loss: {avg_loss:.4f} | "
                        f"PPL: {perplexity:.2f} | "
                        f"LR: {lr:.2e} | "
                        f"Time: {elapsed:.0f}s"
                    )
                    accumulated_loss = 0.0

                    if self._cloud_sync:
                        self._cloud_sync.upload_training_log(log_entry, step=self.global_step)

                if self.global_step % self.config["save_every_steps"] == 0:
                    avg_loss = sum(e["loss"] for e in self.training_log[-10:]) / max(len(self.training_log[-10:]), 1)
                    if avg_loss < self.best_loss:
                        self.best_loss = avg_loss

                    cp_path = self._save_checkpoint(optimizer, avg_loss)

                    if self.global_step % self.config["upload_every_steps"] == 0:
                        self._upload_checkpoint(cp_path, avg_loss)

            if self.global_step >= self.config["max_steps"]:
                break

        total_time = time.time() - start_time
        final_loss = self.training_log[-1]["loss"] if self.training_log else 0.0

        report = {
            "total_steps": self.global_step,
            "final_loss": final_loss,
            "best_loss": self.best_loss,
            "total_training_time_seconds": round(total_time, 1),
            "device": str(self.device),
            "dataset_size": len(dataset),
            "training_log_entries": len(self.training_log),
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ اكتمل التدريب!")
        logger.info(f"   Steps: {self.global_step}")
        logger.info(f"   Final Loss: {final_loss:.4f}")
        logger.info(f"   Best Loss: {self.best_loss:.4f}")
        logger.info(f"   Time: {total_time:.0f}s")

        if self._cloud_sync:
            self._cloud_sync.upload_training_report(report)
            self._cloud_sync.stop_auto_sync()

        return report
