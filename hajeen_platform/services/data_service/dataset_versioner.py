"""Dataset Versioner — Phase 4 — إدارة إصدارات الـ datasets."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DatasetVersion:
    version_id: str
    name: str
    version: str
    record_count: int
    size_bytes: int
    format: str
    checksum: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)
    path: str = ""
    is_train: bool = False
    is_valid: bool = False

    def to_dict(self) -> Dict:
        return {
            "version_id": self.version_id,
            "name": self.name,
            "version": self.version,
            "record_count": self.record_count,
            "size_bytes": self.size_bytes,
            "format": self.format,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "path": self.path,
        }


class DatasetVersioner:
    """
    إدارة إصدارات الـ datasets مع:
    - dataset versioning بـ checksum
    - train/validation split
    - quality filtering
    - duplicate removal
    - JSONL + Parquet export
    - HuggingFace compatibility
    - metadata preservation
    - embedding-ready export
    """

    def __init__(self, base_dir: str = "storage_data/datasets") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._base / "versions.json"
        self._versions: Dict[str, DatasetVersion] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if self._registry_path.exists():
            try:
                data = json.loads(self._registry_path.read_text())
                for vid, entry in data.items():
                    self._versions[vid] = DatasetVersion(**entry)
            except Exception as exc:
                logger.warning("فشل تحميل registry: %s", exc)

    def _save_registry(self) -> None:
        data = {vid: v.to_dict() for vid, v in self._versions.items()}
        self._registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    # ─── Build ────────────────────────────────────────────────────────────────

    def create_version(
        self,
        records: List[Dict],
        name: str,
        version: str = "v1.0",
        fmt: str = "jsonl",
        metadata: Optional[Dict] = None,
    ) -> DatasetVersion:
        """يُنشئ إصداراً جديداً من الـ records."""
        if not records:
            raise ValueError("لا يمكن إنشاء dataset فارغ")

        # Quality filtering
        records = self._quality_filter(records)

        # Deduplication
        records = self._deduplicate(records)

        # Compute checksum
        checksum = self._checksum(records)
        version_id = f"{name}_{version}_{checksum[:8]}"

        # Check if same checksum exists
        for v in self._versions.values():
            if v.checksum == checksum and v.name == name:
                logger.info("Dataset مطابق موجود: %s", v.version_id)
                return v

        # Save
        version_dir = self._base / version_id
        version_dir.mkdir(exist_ok=True)

        path = self._save_records(records, version_dir, name, fmt)
        size = os.path.getsize(path)

        ver = DatasetVersion(
            version_id=version_id,
            name=name,
            version=version,
            record_count=len(records),
            size_bytes=size,
            format=fmt,
            checksum=checksum,
            metadata=metadata or {},
            path=str(path),
        )
        self._versions[version_id] = ver
        self._save_registry()

        logger.info(
            "Dataset version created: %s records=%d size=%.1fKB",
            version_id, len(records), size / 1024,
        )
        return ver

    def split(
        self,
        records: List[Dict],
        train_ratio: float = 0.9,
        shuffle: bool = True,
        seed: int = 42,
    ) -> tuple:
        """تقسيم إلى train/validation."""
        import random
        rng = random.Random(seed)
        data = list(records)
        if shuffle:
            rng.shuffle(data)
        split_idx = int(len(data) * train_ratio)
        return data[:split_idx], data[split_idx:]

    # ─── Export ───────────────────────────────────────────────────────────────

    def export_jsonl(self, records: List[Dict], path: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger.info("JSONL export: %s (%d records)", path, len(records))
        return str(p)

    def export_parquet(self, records: List[Dict], path: str) -> str:
        try:
            import pandas as pd
            df = pd.DataFrame(records)
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(str(p), index=False, engine="pyarrow")
            logger.info("Parquet export: %s (%d records)", path, len(records))
            return str(p)
        except ImportError:
            logger.warning("pandas/pyarrow غير متاح — تصدير كـ JSONL بدلاً")
            return self.export_jsonl(records, path.replace(".parquet", ".jsonl"))

    def export_huggingface(self, records: List[Dict], path: str, split: str = "train") -> str:
        """تصدير بصيغة HuggingFace DatasetDict."""
        hf_path = Path(path) / split
        hf_path.mkdir(parents=True, exist_ok=True)
        jsonl_path = hf_path / "data.jsonl"
        self.export_jsonl(records, str(jsonl_path))
        # metadata
        meta = {
            "split": split,
            "num_examples": len(records),
            "features": list(records[0].keys()) if records else [],
        }
        (hf_path / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2)
        )
        logger.info("HuggingFace export: %s split=%s", path, split)
        return str(hf_path)

    def export_embedding_ready(
        self,
        records: List[Dict],
        text_field: str = "text",
        path: str = "storage_data/datasets/embedding_ready.jsonl",
    ) -> str:
        """تصدير بصيغة جاهزة للـ embedding."""
        ready = []
        for r in records:
            text = r.get(text_field) or r.get("content") or r.get("instruction", "")
            if text:
                ready.append({
                    "id": r.get("id", ""),
                    "text": str(text)[:8192],
                    "metadata": {k: v for k, v in r.items() if k not in (text_field, "id")},
                })
        return self.export_jsonl(ready, path)

    # ─── Internal ────────────────────────────────────────────────────────────

    def _quality_filter(self, records: List[Dict]) -> List[Dict]:
        filtered = []
        for r in records:
            text = (r.get("text") or r.get("content") or
                    r.get("instruction") or r.get("response") or
                    r.get("input") or "")
            if len(str(text).strip()) >= 5:
                filtered.append(r)
        removed = len(records) - len(filtered)
        if removed:
            logger.debug("Quality filter: removed %d low-quality records", removed)
        return filtered

    def _deduplicate(self, records: List[Dict]) -> List[Dict]:
        seen: set = set()
        unique = []
        for r in records:
            key_text = r.get("text") or r.get("content") or r.get("instruction", "")
            key = hashlib.md5(str(key_text).encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                unique.append(r)
        removed = len(records) - len(unique)
        if removed:
            logger.debug("Deduplication: removed %d duplicates", removed)
        return unique

    @staticmethod
    def _checksum(records: List[Dict]) -> str:
        content = json.dumps(records, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def _save_records(
        self,
        records: List[Dict],
        directory: Path,
        name: str,
        fmt: str,
    ) -> Path:
        path = directory / f"{name}.{fmt}"
        if fmt == "jsonl":
            with path.open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        elif fmt == "json":
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        else:
            with path.open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return path

    def list_versions(self) -> List[Dict]:
        return [v.to_dict() for v in sorted(
            self._versions.values(), key=lambda v: v.created_at, reverse=True
        )]

    def get_version(self, version_id: str) -> Optional[DatasetVersion]:
        return self._versions.get(version_id)

    def delete_version(self, version_id: str) -> bool:
        ver = self._versions.pop(version_id, None)
        if ver and ver.path:
            version_dir = Path(ver.path).parent
            if version_dir.exists():
                shutil.rmtree(version_dir, ignore_errors=True)
        if ver:
            self._save_registry()
        return ver is not None
