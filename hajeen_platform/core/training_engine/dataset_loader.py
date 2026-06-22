from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class DatasetLoader:
    """Load datasets from JSONL, JSON, Parquet, or HuggingFace Hub."""

    def load_jsonl(self, path: str) -> List[Dict]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Dataset file not found: {path}")
        records: List[Dict] = []
        with p.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning("Line %d parse error: %s", i, exc)
        logger.info("Loaded %d records from %s", len(records), path)
        return records

    def load_json(self, path: str) -> Union[List[Dict], Dict]:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        return data

    def load_parquet(self, path: str) -> Any:
        try:
            import pandas as pd  # type: ignore
            df = pd.read_parquet(path)
            return df.to_dict(orient="records")
        except ImportError as exc:
            raise RuntimeError("pandas + pyarrow required for parquet") from exc

    def load_hf_dataset(
        self,
        dataset_name: str,
        split: str = "train",
        subset: Optional[str] = None,
        max_samples: Optional[int] = None,
    ) -> Any:
        try:
            from datasets import load_dataset  # type: ignore
            ds = load_dataset(dataset_name, subset, split=split, streaming=max_samples is None)
            if max_samples:
                ds = ds.select(range(min(max_samples, len(ds))))
            logger.info("Loaded HF dataset: %s/%s [%s]", dataset_name, subset or "", split)
            return ds
        except ImportError as exc:
            raise RuntimeError("datasets library required") from exc

    def to_hf_dataset(self, records: List[Dict]) -> Any:
        try:
            from datasets import Dataset  # type: ignore
            return Dataset.from_list(records)
        except ImportError as exc:
            raise RuntimeError("datasets library required") from exc

    def split_train_eval(
        self, records: List[Dict], eval_ratio: float = 0.1, seed: int = 42
    ) -> tuple[List[Dict], List[Dict]]:
        import random
        rng = random.Random(seed)
        shuffled = list(records)
        rng.shuffle(shuffled)
        split_idx = max(1, int(len(shuffled) * (1 - eval_ratio)))
        return shuffled[:split_idx], shuffled[split_idx:]
