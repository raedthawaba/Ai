from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Optional


class TokenMetrics:
    """Track token usage by model, user, and time period."""

    def __init__(self) -> None:
        self._usage: List[Dict] = []
        self._by_model: Dict[str, Dict[str, int]] = defaultdict(lambda: {"prompt": 0, "completion": 0})
        self._by_session: Dict[str, Dict[str, int]] = defaultdict(lambda: {"prompt": 0, "completion": 0})
        self._daily: Dict[str, Dict[str, int]] = defaultdict(lambda: {"prompt": 0, "completion": 0})

    def record(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: Optional[str] = None,
    ) -> None:
        entry = {
            "model_id": model_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "session_id": session_id or "",
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d"),
        }
        self._usage.append(entry)
        self._by_model[model_id]["prompt"] += prompt_tokens
        self._by_model[model_id]["completion"] += completion_tokens
        today = entry["date"]
        self._daily[today]["prompt"] += prompt_tokens
        self._daily[today]["completion"] += completion_tokens
        if session_id:
            self._by_session[session_id]["prompt"] += prompt_tokens
            self._by_session[session_id]["completion"] += completion_tokens

    def total_tokens(self) -> int:
        return sum(e["total_tokens"] for e in self._usage)

    def tokens_per_second(self, window_seconds: float = 60.0) -> float:
        now = time.time()
        recent = [e for e in self._usage if now - e["timestamp"] <= window_seconds]
        total = sum(e["completion_tokens"] for e in recent)
        return round(total / window_seconds, 2)

    def model_summary(self) -> Dict:
        return {
            model: {
                "prompt_tokens": counts["prompt"],
                "completion_tokens": counts["completion"],
                "total_tokens": counts["prompt"] + counts["completion"],
            }
            for model, counts in self._by_model.items()
        }

    def daily_summary(self) -> Dict:
        return {
            date: {
                "prompt_tokens": counts["prompt"],
                "completion_tokens": counts["completion"],
                "total_tokens": counts["prompt"] + counts["completion"],
            }
            for date, counts in sorted(self._daily.items(), reverse=True)
        }

    def overall_summary(self) -> Dict:
        total = self.total_tokens()
        return {
            "total_tokens": total,
            "total_prompt_tokens": sum(e["prompt_tokens"] for e in self._usage),
            "total_completion_tokens": sum(e["completion_tokens"] for e in self._usage),
            "requests_recorded": len(self._usage),
            "tokens_per_second_1min": self.tokens_per_second(60),
            "unique_models": len(self._by_model),
        }
