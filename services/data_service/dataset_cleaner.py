from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Dict, List, Optional, Set


class DatasetCleaner:
    """Clean, deduplicate, and filter training datasets."""

    def __init__(
        self,
        min_length: int = 10,
        max_length: int = 32_000,
        remove_duplicates: bool = True,
        min_quality: float = 0.0,
    ) -> None:
        self.min_length = min_length
        self.max_length = max_length
        self.remove_duplicates = remove_duplicates
        self.min_quality = min_quality
        self._seen_hashes: Set[str] = set()

    def clean_text(self, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u0080-\uFFFF]", "", text)
        return text.strip()

    def clean_record(self, record: Dict) -> Optional[Dict]:
        cleaned = {}
        for key, value in record.items():
            if isinstance(value, str):
                cleaned[key] = self.clean_text(value)
            else:
                cleaned[key] = value
        main_text = cleaned.get("text") or cleaned.get("instruction") or cleaned.get("content", "")
        if len(main_text) < self.min_length:
            return None
        if len(main_text) > self.max_length:
            cleaned[next(k for k in ["text", "instruction", "content"] if k in cleaned)] = main_text[:self.max_length]
        return cleaned

    def deduplicate(self, records: List[Dict], field: str = "text") -> List[Dict]:
        unique: List[Dict] = []
        seen: Set[str] = set()
        for rec in records:
            text = str(rec.get(field, rec.get("instruction", rec.get("content", ""))))
            h = hashlib.md5(text.lower().strip().encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                unique.append(rec)
        return unique

    def filter_by_language(self, records: List[Dict], allowed: List[str]) -> List[Dict]:
        try:
            from langdetect import detect  # type: ignore
            result = []
            for rec in records:
                text = rec.get("text", rec.get("instruction", ""))
                try:
                    lang = detect(text)
                    if lang in allowed:
                        result.append(rec)
                except Exception:
                    result.append(rec)
            return result
        except ImportError:
            return records

    def process(self, records: List[Dict]) -> List[Dict]:
        cleaned = [self.clean_record(r) for r in records]
        cleaned = [r for r in cleaned if r is not None]
        if self.remove_duplicates:
            for field in ["text", "instruction", "content"]:
                if any(field in r for r in cleaned):
                    cleaned = self.deduplicate(cleaned, field)
                    break
        return cleaned
