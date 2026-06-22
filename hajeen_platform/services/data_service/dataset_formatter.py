from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class DatasetFormatter:
    """Convert raw records to various training formats."""

    @staticmethod
    def to_alpaca(record: Dict) -> Dict:
        return {
            "instruction": record.get("instruction", ""),
            "input": record.get("input", ""),
            "output": record.get("response", record.get("output", "")),
        }

    @staticmethod
    def to_alpaca_text(record: Dict) -> str:
        instruction = record.get("instruction", "")
        input_text = record.get("input", "")
        output = record.get("response", record.get("output", ""))
        if input_text:
            return (
                f"### Instruction:\n{instruction}\n\n"
                f"### Input:\n{input_text}\n\n"
                f"### Response:\n{output}"
            )
        return f"### Instruction:\n{instruction}\n\n### Response:\n{output}"

    @staticmethod
    def to_chatml(record: Dict) -> str:
        messages = record.get("messages", [])
        if not messages:
            instruction = record.get("instruction", "")
            response = record.get("response", record.get("output", ""))
            messages = [
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": response},
            ]
        parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        return "\n".join(parts)

    @staticmethod
    def to_llama3(record: Dict) -> str:
        instruction = record.get("instruction", "")
        response = record.get("response", record.get("output", ""))
        return (
            f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n{instruction}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n{response}<|eot_id|>"
        )

    @staticmethod
    def to_mistral(record: Dict) -> str:
        instruction = record.get("instruction", "")
        response = record.get("response", record.get("output", ""))
        return f"[INST] {instruction} [/INST] {response}</s>"

    def batch_format(
        self,
        records: List[Dict],
        fmt: str = "alpaca_text",
        custom_fn: Optional[Callable[[Dict], Any]] = None,
    ) -> List[Dict]:
        format_map = {
            "alpaca": self.to_alpaca,
            "alpaca_text": lambda r: {"text": self.to_alpaca_text(r)},
            "chatml": lambda r: {"text": self.to_chatml(r)},
            "llama3": lambda r: {"text": self.to_llama3(r)},
            "mistral": lambda r: {"text": self.to_mistral(r)},
        }
        fn = custom_fn or format_map.get(fmt)
        if fn is None:
            raise ValueError(f"Unsupported format: {fmt}. Choose from {list(format_map)}")
        return [fn(r) for r in records]
