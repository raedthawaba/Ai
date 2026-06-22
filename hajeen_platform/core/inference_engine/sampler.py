from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple


class Sampler:
    """Token sampling strategies: top-k, top-p (nucleus), temperature."""

    @staticmethod
    def temperature_scale(logits: List[float], temperature: float) -> List[float]:
        if temperature <= 0:
            raise ValueError("Temperature must be > 0")
        return [l / temperature for l in logits]

    @staticmethod
    def top_k_filter(logits: List[float], k: int) -> List[float]:
        if k <= 0 or k >= len(logits):
            return logits
        sorted_indices = sorted(range(len(logits)), key=lambda i: logits[i], reverse=True)
        cutoff = logits[sorted_indices[k - 1]]
        return [l if l >= cutoff else float("-inf") for l in logits]

    @staticmethod
    def top_p_filter(logits: List[float], p: float) -> List[float]:
        if p >= 1.0:
            return logits
        probs = Sampler.softmax(logits)
        sorted_pairs = sorted(enumerate(probs), key=lambda x: x[1], reverse=True)
        cumulative = 0.0
        keep: set = set()
        for idx, prob in sorted_pairs:
            cumulative += prob
            keep.add(idx)
            if cumulative >= p:
                break
        return [l if i in keep else float("-inf") for i, l in enumerate(logits)]

    @staticmethod
    def softmax(logits: List[float]) -> List[float]:
        max_l = max(logits)
        exp_vals = [math.exp(l - max_l) for l in logits]
        total = sum(exp_vals)
        return [e / total for e in exp_vals]

    @staticmethod
    def sample(probs: List[float], seed: Optional[int] = None) -> int:
        rng = random.Random(seed)
        r = rng.random()
        cumulative = 0.0
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                return i
        return len(probs) - 1

    @classmethod
    def sample_token(
        cls,
        logits: List[float],
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: Optional[int] = None,
    ) -> int:
        if temperature != 1.0:
            logits = cls.temperature_scale(logits, temperature)
        if top_k > 0:
            logits = cls.top_k_filter(logits, top_k)
        if top_p < 1.0:
            logits = cls.top_p_filter(logits, top_p)
        probs = cls.softmax(logits)
        return cls.sample(probs, seed)

    @staticmethod
    def greedy(logits: List[float]) -> int:
        return logits.index(max(logits))

    @staticmethod
    def repetition_penalty_apply(
        logits: List[float],
        generated_ids: List[int],
        penalty: float = 1.1,
    ) -> List[float]:
        if penalty == 1.0 or not generated_ids:
            return logits
        result = list(logits)
        for token_id in set(generated_ids):
            if token_id < len(result):
                if result[token_id] < 0:
                    result[token_id] *= penalty
                else:
                    result[token_id] /= penalty
        return result
