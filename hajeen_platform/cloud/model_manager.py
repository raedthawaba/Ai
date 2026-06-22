"""
model_manager.py — HuggingFace Model Manager
رفع وتحميل model weights, checkpoints, tokenizer, config
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .hf_client import HFClient

load_dotenv()
logger = logging.getLogger(__name__)


class ModelManager:
    """
    مدير النموذج: رفع وتحميل الأوزان، الـ checkpoints، الـ tokenizer.
    """

    TOKENIZER_FILES = [
        "tokenizer.json",
        "vocab.json",
        "merges.txt",
        "tokenizer_config.json",
        "special_tokens_map.json",
    ]

    CONFIG_FILES = [
        "config.json",
        "generation_config.json",
        "model_card.md",
    ]

    def __init__(self, hf_client: Optional[HFClient] = None):
        self.client = hf_client or HFClient()
        self.model_repo = self.client.model_repo
        self.checkpoint_dir = Path(
            os.getenv("CHECKPOINT_DIR", "./checkpoints")
        )
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ModelManager جاهز. Checkpoint dir: {self.checkpoint_dir}")

    def upload_checkpoint(
        self,
        checkpoint_path: str,
        step: int,
        epoch: Optional[int] = None,
        metrics: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        رفع checkpoint إلى HuggingFace.

        Args:
            checkpoint_path: مسار ملف أو مجلد الـ checkpoint
            step:   رقم الـ step الحالي
            epoch:  رقم الـ epoch (اختياري)
            metrics: مقاييس التدريب (loss, perplexity...)

        Returns:
            رابط الـ checkpoint المرفوع
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ep_str = f"epoch{epoch}_" if epoch is not None else ""
        repo_folder = f"checkpoints/{ep_str}step{step}_{ts}"

        logger.info(f"⬆️  رفع checkpoint step={step} → {repo_folder}")

        cp_path = Path(checkpoint_path)
        if cp_path.is_dir():
            url = self.client.upload_folder(
                local_folder=str(cp_path),
                repo_folder=repo_folder,
                repo_type="model",
                commit_message=f"[Hajeen] Checkpoint step={step}",
            )
        else:
            url = self.client.upload_file(
                local_path=str(cp_path),
                repo_path=f"{repo_folder}/{cp_path.name}",
                repo_type="model",
                commit_message=f"[Hajeen] Checkpoint step={step}",
            )

        if metrics:
            self._upload_metrics(metrics, step, repo_folder)

        return url

    def _upload_metrics(
        self, metrics: Dict[str, float], step: int, repo_folder: str
    ) -> None:
        """رفع مقاييس التدريب بصيغة JSON."""
        tmp = Path(f"/tmp/metrics_step{step}.json")
        payload = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            **metrics,
        }
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        try:
            self.client.upload_file(
                local_path=str(tmp),
                repo_path=f"{repo_folder}/metrics.json",
                repo_type="model",
                commit_message=f"[Hajeen] Metrics step={step}",
            )
        finally:
            tmp.unlink(missing_ok=True)

    def download_checkpoint(
        self,
        step: Optional[int] = None,
        local_dir: Optional[str] = None,
    ) -> str:
        """
        تحميل checkpoint من HuggingFace.
        إذا لم يُحدَّد step يتم تحميل آخر checkpoint.
        """
        from huggingface_hub import snapshot_download

        local_dir = local_dir or str(self.checkpoint_dir / "resumed")
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        pattern = f"checkpoints/*step{step}*" if step else "checkpoints/*"
        logger.info(f"⬇️  تحميل checkpoint — pattern: {pattern}")

        try:
            local_path = snapshot_download(
                repo_id=self.model_repo,
                local_dir=local_dir,
                ignore_patterns=["*.safetensors", "*.bin"],
                token=self.client.token or None,
                allow_patterns=[pattern, "*/metrics.json"],
            )
            logger.info(f"✅ تم تحميل checkpoint: {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"❌ فشل تحميل checkpoint: {e}")
            raise

    def upload_final_weights(
        self,
        weights_dir: str,
        version: str = "v1.0",
        commit_message: Optional[str] = None,
    ) -> str:
        """
        رفع الأوزان النهائية للنموذج.
        """
        msg = commit_message or f"[Hajeen] Final model weights — {version}"
        repo_folder = f"model/{version}"
        logger.info(f"⬆️  رفع الأوزان النهائية — {version}")

        url = self.client.upload_folder(
            local_folder=weights_dir,
            repo_folder=repo_folder,
            repo_type="model",
            commit_message=msg,
        )
        logger.info(f"✅ تم رفع الأوزان: {url}")
        return url

    def upload_tokenizer(
        self,
        tokenizer_dir: str,
        version: str = "v1.0",
    ) -> Dict[str, str]:
        """
        رفع ملفات الـ tokenizer إلى HuggingFace.
        يتحقق من وجود الملفات الأساسية قبل الرفع.
        """
        tokenizer_path = Path(tokenizer_dir)
        uploaded: Dict[str, str] = {}

        for fname in self.TOKENIZER_FILES:
            fpath = tokenizer_path / fname
            if not fpath.exists():
                logger.warning(f"⚠️  {fname} غير موجود — تخطّي")
                continue
            try:
                url = self.client.upload_file(
                    local_path=str(fpath),
                    repo_path=f"tokenizer/{version}/{fname}",
                    repo_type="model",
                    commit_message=f"[Hajeen] Tokenizer {fname} — {version}",
                )
                uploaded[fname] = url
                logger.info(f"✅ {fname} → {url}")
            except Exception as e:
                logger.error(f"❌ فشل رفع {fname}: {e}")
                uploaded[fname] = f"error: {e}"

        return uploaded

    def upload_config(
        self,
        config_dir: str,
        version: str = "v1.0",
    ) -> Dict[str, str]:
        """رفع ملفات الـ config."""
        config_path = Path(config_dir)
        uploaded: Dict[str, str] = {}

        for fname in self.CONFIG_FILES:
            fpath = config_path / fname
            if not fpath.exists():
                continue
            try:
                url = self.client.upload_file(
                    local_path=str(fpath),
                    repo_path=f"configs/{version}/{fname}",
                    repo_type="model",
                    commit_message=f"[Hajeen] Config {fname} — {version}",
                )
                uploaded[fname] = url
            except Exception as e:
                logger.error(f"❌ فشل رفع {fname}: {e}")
        return uploaded

    def list_checkpoints(self) -> List[Dict[str, str]]:
        """عرض قائمة الـ checkpoints المتاحة في HuggingFace."""
        files = self.client.list_repo_files(repo_type="model")
        checkpoints = []
        seen = set()
        for f in files:
            if f.startswith("checkpoints/"):
                parts = f.split("/")
                if len(parts) >= 2:
                    name = parts[1]
                    if name not in seen:
                        seen.add(name)
                        checkpoints.append({"name": name, "path": f"checkpoints/{name}"})
        return checkpoints

    def get_latest_checkpoint_step(self) -> Optional[int]:
        """الحصول على رقم آخر step محفوظ."""
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        steps = []
        for cp in checkpoints:
            name = cp["name"]
            for part in name.split("_"):
                if part.startswith("step"):
                    try:
                        steps.append(int(part[4:]))
                    except ValueError:
                        pass
        return max(steps) if steps else None
