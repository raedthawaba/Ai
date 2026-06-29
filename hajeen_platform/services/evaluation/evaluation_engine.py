from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from hajeen_platform.services.agents.base_agent import AgentResult
from hajeen_platform.services.evaluation.metrics import (
    agent_success_rate_metric,
    hallucination_metric,
    latency_metric,
    tool_accuracy_metric,
)

logger = logging.getLogger(__name__)


class EvaluationEngine:
    """
    Comprehensive AI evaluation framework.
    Supports:
    - Per-result metric evaluation (hallucination, success, latency, tool accuracy)
    - Custom metric registration
    - Named benchmark suites
    - Batch evaluation with aggregated reports
    - Automated evaluation on every result
    """

    DEFAULT_METRICS: Dict[str, Callable] = {
        "hallucination": hallucination_metric,
        "success_rate": agent_success_rate_metric,
        "latency": latency_metric,
        "tool_accuracy": tool_accuracy_metric,
    }

    def __init__(self, enable_defaults: bool = True) -> None:
        self._metrics: Dict[str, Callable] = {}
        self._benchmarks: Dict[str, Callable] = {}
        self._history: List[Dict[str, Any]] = []
        if enable_defaults:
            self._metrics.update(self.DEFAULT_METRICS)
        logger.info(
            "EvaluationEngine initialised with %d metrics.", len(self._metrics)
        )

    # ── Registration ─────────────────────────────────────────────────────

    def register_metric(self, name: str, metric_fn: Callable) -> None:
        """Register a custom metric function: (AgentResult) -> Dict."""
        self._metrics[name] = metric_fn
        logger.debug("Metric '%s' registered.", name)

    def register_benchmark(self, name: str, benchmark_fn: Callable) -> None:
        """Register a benchmark suite function: (**kwargs) -> Dict."""
        self._benchmarks[name] = benchmark_fn
        logger.debug("Benchmark '%s' registered.", name)

    # ── Single Result Evaluation ──────────────────────────────────────────

    async def evaluate_agent_result(
        self, agent_result: AgentResult, tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single AgentResult against all registered metrics.
        Results are stored in evaluation history.
        """
        eval_start = time.perf_counter()
        scores: Dict[str, Any] = {}

        for metric_name, metric_fn in self._metrics.items():
            try:
                if asyncio.iscoroutinefunction(metric_fn):
                    score = await metric_fn(agent_result)
                else:
                    score = metric_fn(agent_result)
                scores[metric_name] = score
            except Exception as exc:
                logger.error("Metric '%s' failed: %s", metric_name, exc)
                scores[metric_name] = {"error": str(exc)}

        eval_ms = round((time.perf_counter() - eval_start) * 1000, 2)
        report = {
            "tag": tag,
            "success": agent_result.success,
            "scores": scores,
            "eval_duration_ms": eval_ms,
            "agent_duration_ms": agent_result.total_duration_ms,
            "steps": len(agent_result.steps),
        }
        self._history.append(report)
        logger.info(
            "Evaluation complete (tag=%s) — %d metrics in %.0f ms.",
            tag, len(scores), eval_ms,
        )
        return report

    # ── Batch Evaluation ──────────────────────────────────────────────────

    async def evaluate_batch(
        self, results: List[AgentResult], tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a list of AgentResults and return aggregate statistics.
        """
        tags = tags or [None] * len(results)
        individual = await asyncio.gather(
            *[self.evaluate_agent_result(r, t) for r, t in zip(results, tags)]
        )

        # Aggregate per metric
        aggregated: Dict[str, Any] = {}
        for metric_name in self._metrics:
            values = []
            for report in individual:
                score = report["scores"].get(metric_name, {})
                if isinstance(score, dict):
                    v = score.get("score", score.get("latency_ms"))
                else:
                    v = score
                if isinstance(v, (int, float)):
                    values.append(v)
            if values:
                aggregated[metric_name] = {
                    "mean": round(sum(values) / len(values), 4),
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "samples": len(values),
                }

        return {
            "total": len(results),
            "succeeded": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "aggregated": aggregated,
            "individual": individual,
        }

    # ── Benchmarks ────────────────────────────────────────────────────────

    async def run_benchmark(self, benchmark_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a named benchmark suite and return results."""
        fn = self._benchmarks.get(benchmark_name)
        if fn is None:
            raise ValueError(f"Benchmark '{benchmark_name}' not registered.")

        logger.info("Running benchmark: %s", benchmark_name)
        start = time.perf_counter()
        try:
            results = await fn(**kwargs) if asyncio.iscoroutinefunction(fn) else fn(**kwargs)
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            logger.info("Benchmark '%s' completed in %.0f ms.", benchmark_name, elapsed)
            return {
                "benchmark": benchmark_name,
                "results": results,
                "elapsed_ms": elapsed,
                "success": True,
            }
        except Exception as exc:
            logger.error("Benchmark '%s' failed: %s", benchmark_name, exc)
            return {
                "benchmark": benchmark_name,
                "success": False,
                "error": str(exc),
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
            }

    async def run_all_benchmarks(self, **kwargs) -> Dict[str, Any]:
        """Run every registered benchmark and aggregate results."""
        results = {}
        for name in self._benchmarks:
            results[name] = await self.run_benchmark(name, **kwargs)
        passed = sum(1 for r in results.values() if r.get("success"))
        return {
            "total_benchmarks": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "results": results,
        }

    # ── History & Reporting ───────────────────────────────────────────────

    def get_history(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._history[-last_n:] if last_n else list(self._history)

    def summary_report(self) -> Dict[str, Any]:
        if not self._history:
            return {"total_evaluations": 0}
        successes = sum(1 for h in self._history if h.get("success"))
        return {
            "total_evaluations": len(self._history),
            "success_rate": round(successes / len(self._history), 3),
            "avg_agent_ms": round(
                sum(h.get("agent_duration_ms", 0) for h in self._history) / len(self._history), 2
            ),
        }
