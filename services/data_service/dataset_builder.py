from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Build structured training datasets from raw text sources."""

    def __init__(self, output_dir: str = "storage_data/datasets") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_instruction_dataset(
        self,
        raw_items: List[Dict],
        instruction_fn: Callable[[Dict], str],
        response_fn: Callable[[Dict], str],
        input_fn: Optional[Callable[[Dict], str]] = None,
        quality_threshold: float = 0.0,
    ) -> List[Dict]:
        records: List[Dict] = []
        for item in raw_items:
            try:
                instruction = instruction_fn(item).strip()
                response = response_fn(item).strip()
                if not instruction or not response:
                    continue
                if len(instruction) < 10 or len(response) < 5:
                    continue
                rec: Dict = {
                    "id": str(uuid.uuid4()),
                    "instruction": instruction,
                    "response": response,
                    "created_at": time.time(),
                }
                if input_fn is not None:
                    rec["input"] = input_fn(item).strip()
                if quality_threshold > 0:
                    score = self._quality_score(instruction, response)
                    if score < quality_threshold:
                        continue
                    rec["quality_score"] = score
                records.append(rec)
            except Exception as exc:
                logger.debug("Skipping item due to error: %s", exc)
        logger.info("Built %d instruction records", len(records))
        return records

    def build_chat_dataset(
        self, conversations: List[List[Dict]]
    ) -> List[Dict]:
        records: List[Dict] = []
        for convo in conversations:
            if len(convo) < 2:
                continue
            records.append(
                {
                    "id": str(uuid.uuid4()),
                    "messages": convo,
                    "turn_count": len(convo),
                    "created_at": time.time(),
                }
            )
        return records

    def save(self, records: List[Dict], name: str, fmt: str = "jsonl") -> str:
        ext = fmt if fmt.startswith(".") else f".{fmt}"
        path = self.output_dir / f"{name}{ext}"
        if fmt == "jsonl":
            with path.open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        elif fmt == "json":
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved %d records to %s", len(records), path)
        return str(path)

    @staticmethod
    def _quality_score(instruction: str, response: str) -> float:
        score = 0.5
        if len(response) > 50:
            score += 0.2
        if len(response) > 200:
            score += 0.1
        if "?" in instruction:
            score += 0.1
        if len(set(instruction.lower().split()) & set(response.lower().split())) > 2:
            score += 0.1
        return min(1.0, score)
