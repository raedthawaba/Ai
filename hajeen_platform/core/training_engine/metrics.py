from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepMetrics:
    step: int
    loss: float
    learning_rate: float
    epoch: float
    tokens_per_second: float = 0.0
    grad_norm: float = 0.0
    timestamp: float = field(default_factory=time.time)


class TrainingMetrics:
    """Collects and computes training metrics over time."""

    def __init__(self) -> None:
        self._steps: List[StepMetrics] = []
        self._eval_results: List[Dict] = []
        self._start_time: Optional[float] = None

    def start(self) -> None:
        self._start_time = time.time()

    def record_step(
        self,
        step: int,
        loss: float,
        lr: float,
        epoch: float,
        tokens_per_second: float = 0.0,
        grad_norm: float = 0.0,
    ) -> None:
        self._steps.append(
            StepMetrics(
                step=step,
                loss=loss,
                learning_rate=lr,
                epoch=epoch,
                tokens_per_second=tokens_per_second,
                grad_norm=grad_norm,
            )
        )

    def record_eval(self, metrics: Dict) -> None:
        self._eval_results.append({"timestamp": time.time(), **metrics})

    def current_loss(self) -> Optional[float]:
        if self._steps:
            return self._steps[-1].loss
        return None

    def perplexity(self) -> Optional[float]:
        loss = self.current_loss()
        if loss is not None:
            return round(math.exp(loss), 4)
        return None

    def best_eval_loss(self) -> Optional[float]:
        if not self._eval_results:
            return None
        return min(r.get("eval_loss", float("inf")) for r in self._eval_results)

    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def summary(self) -> Dict:
        return {
            "total_steps": len(self._steps),
            "current_loss": self.current_loss(),
            "perplexity": self.perplexity(),
            "best_eval_loss": self.best_eval_loss(),
            "elapsed_seconds": round(self.elapsed_seconds(), 2),
            "eval_runs": len(self._eval_results),
        }

    def to_history(self) -> List[Dict]:
        return [
            {
                "step": s.step,
                "loss": s.loss,
                "lr": s.learning_rate,
                "epoch": s.epoch,
            }
            for s in self._steps
        ]
