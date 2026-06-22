from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


class ResponseParser:
    """Parse and clean raw LLM output into structured responses."""

    _CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
    _THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
    _JSON_BLOCK_RE = re.compile(r"```json\n?(.*?)```", re.DOTALL)

    @classmethod
    def clean(cls, text: str, stop_sequences: Optional[List[str]] = None) -> str:
        text = cls._THINK_TAG_RE.sub("", text)
        if stop_sequences:
            for seq in stop_sequences:
                idx = text.find(seq)
                if idx != -1:
                    text = text[:idx]
        return text.strip()

    @classmethod
    def extract_code_blocks(cls, text: str) -> List[str]:
        return [m.strip() for m in cls._CODE_BLOCK_RE.findall(text)]

    @classmethod
    def extract_json(cls, text: str) -> Optional[Any]:
        m = cls._JSON_BLOCK_RE.search(text)
        raw = m.group(1) if m else text
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                pass
        return None

    @classmethod
    def extract_list(cls, text: str) -> List[str]:
        items: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            if re.match(r"^[-•*]\s+", line):
                items.append(re.sub(r"^[-•*]\s+", "", line))
            elif re.match(r"^\d+[.)]\s+", line):
                items.append(re.sub(r"^\d+[.)]\s+", "", line))
        return items

    @classmethod
    def to_structured(
        cls,
        raw_text: str,
        prompt: str = "",
        model_id: str = "",
        stop_sequences: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        cleaned = cls.clean(raw_text, stop_sequences)
        return {
            "text": cleaned,
            "raw": raw_text,
            "model": model_id,
            "finish_reason": "stop" if stop_sequences and any(s in raw_text for s in stop_sequences) else "length",
            "prompt_length": len(prompt),
            "completion_length": len(cleaned),
        }
