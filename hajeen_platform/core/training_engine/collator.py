from __future__ import annotations

from typing import Any, Dict, List, Optional


class InstructionDataCollator:
    """Custom data collator for instruction-following datasets."""

    def __init__(
        self,
        tokenizer: Any,
        max_length: int = 2048,
        response_template: str = "### Response:",
        ignore_index: int = -100,
    ) -> None:
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.response_template = response_template
        self.ignore_index = ignore_index
        self._response_ids: Optional[List[int]] = None

    def _get_response_ids(self) -> List[int]:
        if self._response_ids is None:
            self._response_ids = self.tokenizer.encode(
                self.response_template, add_special_tokens=False
            )
        return self._response_ids

    def __call__(self, features: List[Dict]) -> Dict:
        try:
            import torch  # type: ignore

            input_ids_list: List[List[int]] = []
            labels_list: List[List[int]] = []

            for feature in features:
                input_ids = feature["input_ids"]
                labels = list(input_ids)
                response_ids = self._get_response_ids()
                response_start = self._find_sublist(input_ids, response_ids)
                if response_start != -1:
                    for j in range(response_start + len(response_ids)):
                        labels[j] = self.ignore_index
                input_ids_list.append(input_ids)
                labels_list.append(labels)

            max_len = min(self.max_length, max(len(ids) for ids in input_ids_list))
            padded_input = [ids[:max_len] + [self.tokenizer.pad_token_id] * max(0, max_len - len(ids)) for ids in input_ids_list]
            padded_labels = [lbl[:max_len] + [self.ignore_index] * max(0, max_len - len(lbl)) for lbl in labels_list]
            attn_mask = [[1 if t != self.tokenizer.pad_token_id else 0 for t in ids] for ids in padded_input]

            return {
                "input_ids": torch.tensor(padded_input, dtype=torch.long),
                "labels": torch.tensor(padded_labels, dtype=torch.long),
                "attention_mask": torch.tensor(attn_mask, dtype=torch.long),
            }
        except ImportError as exc:
            raise RuntimeError("PyTorch required") from exc

    @staticmethod
    def _find_sublist(lst: List[int], sub: List[int]) -> int:
        for i in range(len(lst) - len(sub) + 1):
            if lst[i: i + len(sub)] == sub:
                return i
        return -1
