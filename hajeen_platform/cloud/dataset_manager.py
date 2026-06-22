"""
dataset_manager.py — HuggingFace Dataset Manager
إدارة تحميل ورفع وتقسيم وتحديث datasets من/إلى HuggingFace
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

from .hf_client import HFClient

load_dotenv()
logger = logging.getLogger(__name__)


class DatasetManager:
    """
    مدير Datasets: تحميل، رفع، تقسيم، تحديث تلقائي.
    يعمل مع HuggingFace Datasets Hub.
    """

    SUPPORTED_SOURCES = [
        "wikipedia",
        "common_crawl",
        "arabic",
        "english",
        "qa",
        "code",
    ]

    def __init__(self, hf_client: Optional[HFClient] = None):
        self.client = hf_client or HFClient()
        self.dataset_repo = self.client.dataset_repo
        self.local_cache_dir = Path(
            os.getenv("DATASET_CACHE_DIR", "./data/hf_datasets")
        )
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"DatasetManager جاهز. Cache: {self.local_cache_dir}")

    def load_from_hub(
        self,
        dataset_name: str,
        split: str = "train",
        streaming: bool = False,
        config_name: Optional[str] = None,
        num_samples: Optional[int] = None,
    ) -> Any:
        """
        تحميل dataset من HuggingFace Hub.

        Args:
            dataset_name: اسم الـ dataset (مثلاً 'Raedthawaba/hajeen-datasets')
            split: الـ split المطلوب ('train', 'validation', 'test')
            streaming: تفعيل streaming لتوفير الذاكرة
            config_name: اسم الـ config إذا وُجد
            num_samples: عدد العينات (None = كل شيء)

        Returns:
            HuggingFace Dataset object
        """
        from datasets import load_dataset

        logger.info(f"⬇️  تحميل dataset: {dataset_name} [{split}]")
        kwargs: Dict[str, Any] = {
            "path": dataset_name,
            "split": split,
            "streaming": streaming,
            "token": self.client.token or None,
        }
        if config_name:
            kwargs["name"] = config_name

        try:
            dataset = load_dataset(**kwargs)
            if num_samples and not streaming:
                dataset = dataset.select(range(min(num_samples, len(dataset))))
            logger.info(f"✅ تم تحميل {dataset_name}: {len(dataset) if not streaming else 'streaming'} عينة")
            return dataset
        except Exception as e:
            logger.error(f"❌ فشل تحميل {dataset_name}: {e}")
            raise

    def load_hajeen_datasets(
        self,
        splits: Optional[List[str]] = None,
        streaming: bool = False,
    ) -> Dict[str, Any]:
        """
        تحميل مجموعة datasets الحاجين من HuggingFace.
        """
        splits = splits or ["train"]
        results = {}
        for split in splits:
            try:
                ds = self.load_from_hub(
                    dataset_name=self.dataset_repo,
                    split=split,
                    streaming=streaming,
                )
                results[split] = ds
            except Exception as e:
                logger.warning(f"⚠️  لم يتم تحميل split '{split}': {e}")
        return results

    def upload_dataset(
        self,
        local_path: Union[str, Path],
        repo_path: str,
        commit_message: Optional[str] = None,
        version_tag: Optional[str] = None,
    ) -> str:
        """
        رفع dataset محلي إلى HuggingFace.

        Args:
            local_path: مسار الملف أو المجلد المحلي
            repo_path: المسار داخل الـ repository
            commit_message: رسالة الـ commit
            version_tag: وسم الإصدار (اختياري)

        Returns:
            رابط الـ dataset المرفوع
        """
        local_path = Path(local_path)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        msg = commit_message or f"[Hajeen] Upload dataset — {ts}"
        if version_tag:
            repo_path = f"versions/{version_tag}/{repo_path}"

        if local_path.is_dir():
            return self.client.upload_folder(
                local_folder=str(local_path),
                repo_folder=repo_path,
                repo_type="dataset",
                commit_message=msg,
            )
        else:
            return self.client.upload_file(
                local_path=str(local_path),
                repo_path=repo_path,
                repo_type="dataset",
                commit_message=msg,
            )

    def upload_cleaned_dataset(
        self,
        data: List[Dict[str, Any]],
        name: str,
        source: str = "unknown",
    ) -> str:
        """
        رفع dataset منظف مباشرةً من الذاكرة.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp_path = self.local_cache_dir / f"{name}_{ts}.jsonl"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for record in data:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        repo_path = f"cleaned/{source}/{name}_{ts}.jsonl"
        logger.info(f"⬆️  رفع dataset منظف: {len(data)} سجل → {repo_path}")
        url = self.upload_dataset(tmp_path, repo_path, commit_message=f"[Hajeen] Cleaned dataset: {name}")
        tmp_path.unlink(missing_ok=True)
        return url

    def split_dataset(
        self,
        dataset: Any,
        train_ratio: float = 0.9,
        val_ratio: float = 0.05,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        تقسيم dataset إلى train/validation/test.
        """
        logger.info(f"تقسيم الـ dataset — train:{train_ratio} val:{val_ratio}")
        split1 = dataset.train_test_split(test_size=(1 - train_ratio), seed=seed)
        remaining = split1["test"]
        val_size = val_ratio / (1 - train_ratio)
        split2 = remaining.train_test_split(test_size=(1 - val_size), seed=seed)

        return {
            "train": split1["train"],
            "validation": split2["train"],
            "test": split2["test"],
        }

    def get_dataset_versions(self) -> List[str]:
        """جلب قائمة إصدارات الـ datasets المرفوعة."""
        files = self.client.list_repo_files(
            repo_id=self.dataset_repo, repo_type="dataset"
        )
        versions = sorted({f.split("/")[1] for f in files if f.startswith("versions/")})
        return versions

    def load_wikipedia(
        self, language: str = "ar", num_samples: Optional[int] = 50000
    ) -> Any:
        """تحميل Wikipedia dataset."""
        logger.info(f"⬇️  Wikipedia [{language}]")
        from datasets import load_dataset
        ds = load_dataset("wikipedia", f"20220301.{language}", split="train", streaming=True, trust_remote_code=True)
        if num_samples:
            ds = ds.take(num_samples)
        return ds

    def load_common_crawl(self, num_samples: int = 10000) -> Any:
        """تحميل Common Crawl (OSCAR Arabic)."""
        logger.info("⬇️  Common Crawl / OSCAR Arabic")
        from datasets import load_dataset
        ds = load_dataset("oscar-corpus/OSCAR-2301", "ar", split="train", streaming=True, trust_remote_code=True)
        return ds.take(num_samples)

    def auto_update_datasets(self) -> Dict[str, str]:
        """تحديث datasets تلقائياً وإعادة رفعها."""
        logger.info("🔄 بدء التحديث التلقائي للـ datasets")
        results = {}
        sources = [("wikipedia_ar", "ar"), ("wikipedia_en", "en")]
        for name, lang in sources:
            try:
                ds = self.load_wikipedia(language=lang, num_samples=5000)
                records = [{"text": r["text"], "source": f"wikipedia_{lang}", "lang": lang}
                           for r in ds]
                url = self.upload_cleaned_dataset(records, name=name, source="wikipedia")
                results[name] = url
            except Exception as e:
                logger.error(f"❌ فشل تحديث {name}: {e}")
                results[name] = f"error: {e}"
        return results
