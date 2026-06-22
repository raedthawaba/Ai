from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatasetExporter:
    """Export datasets to JSONL, JSON, Parquet, and HuggingFace format."""

    def __init__(self, export_dir: str = "storage_data/exports") -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def to_jsonl(self, records: List[Dict], filename: str) -> str:
        path = self.export_dir / f"{filename}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger.info("Exported %d records → JSONL: %s", len(records), path)
        return str(path)

    def to_json(self, records: List[Dict], filename: str) -> str:
        path = self.export_dir / f"{filename}.json"
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Exported %d records → JSON: %s", len(records), path)
        return str(path)

    def to_parquet(self, records: List[Dict], filename: str) -> str:
        try:
            import pandas as pd  # type: ignore
            path = self.export_dir / f"{filename}.parquet"
            df = pd.DataFrame(records)
            df.to_parquet(str(path), index=False)
            logger.info("Exported %d records → Parquet: %s", len(records), path)
            return str(path)
        except ImportError as exc:
            raise RuntimeError("pandas + pyarrow required for Parquet export") from exc

    def to_hf_dataset(self, records: List[Dict], filename: str) -> Any:
        try:
            from datasets import Dataset  # type: ignore
            ds = Dataset.from_list(records)
            path = str(self.export_dir / filename)
            ds.save_to_disk(path)
            logger.info("Exported %d records → HF Dataset: %s", len(records), path)
            return ds
        except ImportError as exc:
            raise RuntimeError("datasets library required") from exc

    def export_all_formats(
        self,
        records: List[Dict],
        basename: str,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        fmts = formats or ["jsonl", "json"]
        paths: Dict[str, str] = {}
        for fmt in fmts:
            if fmt == "jsonl":
                paths["jsonl"] = self.to_jsonl(records, basename)
            elif fmt == "json":
                paths["json"] = self.to_json(records, basename)
            elif fmt == "parquet":
                try:
                    paths["parquet"] = self.to_parquet(records, basename)
                except RuntimeError as exc:
                    logger.warning("Parquet export skipped: %s", exc)
        return paths
