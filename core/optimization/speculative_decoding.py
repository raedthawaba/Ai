"""
Speculative Decoding — uses a small draft model to generate candidate tokens
that are verified in parallel by the large target model for 2-4x speedup.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SpeculativeResult:
    tokens: List[int]
    accepted_count: int
    draft_count: int
    acceptance_rate: float
    latency_ms: float
    speedup_factor: float


class SpeculativeDecoder:
    """Implements speculative decoding with draft + target model pair."""

    def __init__(
        self,
        target_model: Any,
        draft_model: Any,
        draft_steps: int = 4,
        temperature: float = 1.0,
    ) -> None:
        self.target = target_model
        self.draft = draft_model
        self.draft_steps = draft_steps
        self.temperature = temperature
        self._total_accepted = 0
        self._total_drafted = 0

    def generate(
        self,
        input_ids: List[int],
        max_new_tokens: int = 256,
    ) -> SpeculativeResult:
        start = time.perf_counter()
        generated: List[int] = []
        current_ids = list(input_ids)
        total_accepted = 0
        total_drafted = 0

        while len(generated) < max_new_tokens:
            remaining = max_new_tokens - len(generated)
            num_draft = min(self.draft_steps, remaining)

            draft_tokens = self._generate_draft(current_ids, num_draft)
            total_drafted += len(draft_tokens)

            accepted, bonus = self._verify_draft(current_ids, draft_tokens)
            total_accepted += len(accepted)

            generated.extend(accepted)
            current_ids.extend(accepted)

            if bonus is not None:
                generated.append(bonus)
                current_ids.append(bonus)

            if len(accepted) < len(draft_tokens):
                break

        self._total_accepted += total_accepted
        self._total_drafted += total_drafted
        latency_ms = (time.perf_counter() - start) * 1000

        acceptance_rate = total_accepted / total_drafted if total_drafted > 0 else 0.0
        speedup = 1 / (1 - acceptance_rate) if acceptance_rate < 1 else float(self.draft_steps)

        return SpeculativeResult(
            tokens=generated[:max_new_tokens],
            accepted_count=total_accepted,
            draft_count=total_drafted,
            acceptance_rate=round(acceptance_rate, 4),
            latency_ms=round(latency_ms, 2),
            speedup_factor=round(speedup, 2),
        )

    def _generate_draft(self, input_ids: List[int], num_steps: int) -> List[int]:
        try:
            import torch
            with torch.no_grad():
                ids_tensor = torch.tensor([input_ids])
                draft_tokens: List[int] = []
                for _ in range(num_steps):
                    output = self.draft(ids_tensor)
                    logits = output.logits[:, -1, :]
                    if self.temperature > 0:
                        logits = logits / self.temperature
                    probs = torch.softmax(logits, dim=-1)
                    next_token = torch.multinomial(probs, 1).item()
                    draft_tokens.append(next_token)
                    ids_tensor = torch.cat([ids_tensor, torch.tensor([[next_token]])], dim=1)
                return draft_tokens
        except Exception as exc:
            logger.warning("Draft generation failed: %s", exc)
            return []

    def _verify_draft(
        self,
        input_ids: List[int],
        draft_tokens: List[int],
    ) -> Tuple[List[int], Optional[int]]:
        try:
            import torch

            all_ids = input_ids + draft_tokens
            ids_tensor = torch.tensor([all_ids])
            with torch.no_grad():
                output = self.target(ids_tensor)

            logits = output.logits[0]
            accepted: List[int] = []

            for i, draft_token in enumerate(draft_tokens):
                pos = len(input_ids) - 1 + i
                target_probs = torch.softmax(logits[pos] / self.temperature, dim=-1)
                draft_prob = target_probs[draft_token].item()

                if draft_prob > 0.7:
                    accepted.append(draft_token)
                else:
                    bonus_pos = len(input_ids) - 1 + len(accepted)
                    bonus_probs = torch.softmax(logits[bonus_pos] / self.temperature, dim=-1)
                    bonus = torch.multinomial(bonus_probs, 1).item()
                    return accepted, bonus

            bonus_pos = len(input_ids) - 1 + len(accepted)
            if bonus_pos < logits.shape[0]:
                bonus_probs = torch.softmax(logits[bonus_pos] / self.temperature, dim=-1)
                bonus = torch.multinomial(bonus_probs, 1).item()
            else:
                bonus = None
            return accepted, bonus

        except Exception as exc:
            logger.warning("Draft verification failed: %s", exc)
            return draft_tokens[:1], None

    def lifetime_stats(self) -> dict:
        total = self._total_drafted
        return {
            "total_accepted": self._total_accepted,
            "total_drafted": total,
            "lifetime_acceptance_rate": round(self._total_accepted / total, 4) if total > 0 else 0,
        }
