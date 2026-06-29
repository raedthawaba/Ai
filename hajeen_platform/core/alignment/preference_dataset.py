from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class PreferenceExample:
    prompt: str
    chosen: str
    rejected: str
    metadata: Optional[Dict[str, Any]] = None

class PreferenceDatasetBuilder:
    """Builder for DPO/Preference optimization datasets."""

    def __init__(self, output_path: str = "storage_data/alignment/preference_datasets") -> None:
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.examples: List[PreferenceExample] = []

    def add_example(self, prompt: str, chosen: str, rejected: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.examples.append(PreferenceExample(
            prompt=prompt,
            chosen=chosen,
            rejected=rejected,
            metadata=metadata
        ))

    def from_jsonl(self, file_path: str) -> None:
        """Load examples from a JSONL file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                self.add_example(
                    prompt=data["prompt"],
                    chosen=data["chosen"],
                    rejected=data["rejected"],
                    metadata=data.get("metadata")
                )

    def save(self, filename: str) -> str:
        """Save the dataset to a JSONL file."""
        dest = self.output_path / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, 'w', encoding='utf-8') as f:
            for ex in self.examples:
                f.write(json.dumps({
                    "prompt": ex.prompt,
                    "chosen": ex.chosen,
                    "rejected": ex.rejected,
                    "metadata": ex.metadata
                }) + "\n")
        logger.info(f"Preference dataset saved to {dest}")
        return str(dest)

    def clear(self) -> None:
        self.examples = []
