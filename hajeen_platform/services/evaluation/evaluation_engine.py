from __future__ import annotations
import asyncio
import logging
from typing import Dict, Any, List, Callable, Optional
from hajeen_platform.services.agents.base_agent import AgentResult

logger = logging.getLogger(__name__)

class EvaluationEngine:
    """Core engine for running various AI system evaluations."""

    def __init__(self):
        self._metrics: Dict[str, Callable] = {}
        self._benchmarks: Dict[str, Callable] = {}
        logger.info("EvaluationEngine initialized.")

    def register_metric(self, name: str, metric_fn: Callable) -> None:
        self._metrics[name] = metric_fn
        logger.debug(f"Metric '{name}' registered.")

    def register_benchmark(self, name: str, benchmark_fn: Callable) -> None:
        self._benchmarks[name] = benchmark_fn
        logger.debug(f"Benchmark '{name}' registered.")

    async def evaluate_agent_result(self, agent_result: AgentResult) -> Dict[str, Any]:
        """Evaluates a single agent's result against registered metrics."""
        evaluation_results = {}
        for metric_name, metric_fn in self._metrics.items():
            try:
                if asyncio.iscoroutinefunction(metric_fn):
                    score = await metric_fn(agent_result)
                else:
                    score = metric_fn(agent_result)
                evaluation_results[metric_name] = score
            except Exception as e:
                logger.error(f"Error evaluating metric '{metric_name}': {e}")
                evaluation_results[metric_name] = {"error": str(e)}
        return evaluation_results

    async def run_benchmark(self, benchmark_name: str, **kwargs) -> Dict[str, Any]:
        """Runs a registered benchmark and returns its results."""
        benchmark_fn = self._benchmarks.get(benchmark_name)
        if not benchmark_fn:
            raise ValueError(f"Benchmark '{benchmark_name}' not found.")
        
        logger.info(f"Running benchmark: {benchmark_name}")
        try:
            if asyncio.iscoroutinefunction(benchmark_fn):
                results = await benchmark_fn(**kwargs)
            else:
                results = benchmark_fn(**kwargs)
            logger.info(f"Benchmark '{benchmark_name}' completed.")
            return {"benchmark": benchmark_name, "results": results, "success": True}
        except Exception as e:
            logger.error(f"Error running benchmark '{benchmark_name}': {e}")
            return {"benchmark": benchmark_name, "success": False, "error": str(e)}

    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Runs all registered benchmarks."""
        all_benchmark_results = {}
        for benchmark_name in self._benchmarks:
            all_benchmark_results[benchmark_name] = await self.run_benchmark(benchmark_name)
        return all_benchmark_results

