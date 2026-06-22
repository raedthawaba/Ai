from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class HallucinationRecord:
    request_id: str
    query: str
    response: str
    score: float
    flags: List[str]
    timestamp: float = field(default_factory=time.time)


class HallucinationTracker:
    """Detect and track potential hallucinations in LLM outputs."""

    _UNCERTAINTY_PHRASES = [
        "i'm not sure", "i don't know", "i cannot verify",
        "it might be", "possibly", "i believe but am not certain",
    ]
    _FABRICATION_SIGNALS = [
        r"\baccording to\s+\w+\s+\([\d]{4}\)",
        r"as stated in .{0,50} study",
        r"research by .{0,50} shows",
    ]
    _COMPILED_FAB = [re.compile(p, re.I) for p in _FABRICATION_SIGNALS]

    def __init__(self, window_size: int = 200) -> None:
        self._records: List[HallucinationRecord] = []
        self.window_size = window_size

    def check(
        self,
        query: str,
        response: str,
        context: Optional[str] = None,
        request_id: str = "",
    ) -> HallucinationRecord:
        flags: List[str] = []
        score = 0.0

        resp_lower = response.lower()
        for phrase in self._UNCERTAINTY_PHRASES:
            if phrase in resp_lower:
                flags.append("uncertainty_expressed")
                score += 0.1
                break

        for pattern in self._COMPILED_FAB:
            if pattern.search(response):
                flags.append("citation_without_context")
                score += 0.3
                break

        if context:
            context_words = set(context.lower().split())
            response_words = response.lower().split()
            non_context = sum(1 for w in response_words if w not in context_words and len(w) > 5)
            if non_context / max(1, len(response_words)) > 0.7:
                flags.append("low_context_overlap")
                score += 0.2

        if len(response) < 20 and "?" not in response:
            flags.append("suspiciously_short")
            score += 0.1

        record = HallucinationRecord(
            request_id=request_id,
            query=query,
            response=response[:200],
            score=min(1.0, round(score, 3)),
            flags=flags,
        )
        if len(self._records) >= self.window_size:
            self._records = self._records[-self.window_size // 2:]
        self._records.append(record)
        return record

    def summary(self) -> Dict:
        if not self._records:
            return {"total_checked": 0}
        flagged = [r for r in self._records if r.flags]
        return {
            "total_checked": len(self._records),
            "flagged_count": len(flagged),
            "flag_rate": round(len(flagged) / max(1, len(self._records)), 4),
            "avg_score": round(sum(r.score for r in self._records) / len(self._records), 4),
            "top_flags": self._top_flags(),
        }

    def _top_flags(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self._records:
            for flag in r.flags:
                counts[flag] = counts.get(flag, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
