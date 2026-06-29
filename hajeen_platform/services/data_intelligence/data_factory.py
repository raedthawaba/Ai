from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_SYNTHETIC_PROMPT = """Generate {count} high-quality synthetic training examples for the domain: {domain}.

Format: Return a JSON array of objects. Each object must have:
- "instruction": the task or question
- "input": optional context or input (empty string if none)
- "output": the ideal response

Quality requirements:
- Diverse phrasing and topics within the domain
- Realistic, accurate, and helpful responses
- Vary the difficulty level

Respond with a JSON array only — no markdown:
[{{"instruction": "...", "input": "...", "output": "..."}}]"""

_REFINE_PROMPT = """You are a dataset quality specialist. Review the following training example and improve it.

Original:
{example}

Issues to fix:
- Vague or ambiguous instructions → make them specific
- Short or incomplete outputs → expand with detail
- Factual errors → correct them
- Poor formatting → improve structure

Return an improved version as JSON: {{"instruction": "...", "input": "...", "output": "..."}}"""

_LABEL_PROMPT = """Label the following text sample for training.

Text: {text}
Task type: {task_type}

Return ONLY valid JSON:
{{
  "label": "category_name",
  "confidence": 0.95,
  "reasoning": "brief explanation"
}}"""


@dataclass
class DataSample:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    instruction: str = ""
    input: str = ""
    output: str = ""
    label: Optional[str] = None
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutonomousDataFactory:
    """
    Autonomous Data Factory for self-improving datasets.
    Supports:
    - LLM-powered synthetic data generation
    - Automatic dataset refinement / quality improvement
    - Semantic deduplication
    - Automatic labelling
    - Quality scoring
    - Reinforcement data loops
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        self._generators: Dict[str, Callable] = {}
        self._refiners: Dict[str, Callable] = {}
        self._ingestion_pipelines: Dict[str, Callable] = {}
        self._llm = llm
        self._register_builtins()
        logger.info("AutonomousDataFactory initialised (llm=%s).", "present" if llm else "None")

    # ── Registration ────────────────────────────────────────────────────

    def register_generator(self, name: str, generator_fn: Callable) -> None:
        self._generators[name] = generator_fn

    def register_refiner(self, name: str, refiner_fn: Callable) -> None:
        self._refiners[name] = refiner_fn

    def register_ingestion_pipeline(self, name: str, pipeline_fn: Callable) -> None:
        self._ingestion_pipelines[name] = pipeline_fn

    # ── Generation ──────────────────────────────────────────────────────

    async def generate_data(
        self, generator_name: str, config: Dict[str, Any]
    ) -> List[DataSample]:
        fn = self._generators.get(generator_name)
        if fn is None:
            raise ValueError(f"Generator '{generator_name}' not registered.")
        result = await fn(self._llm, **config) if asyncio.iscoroutinefunction(fn) else fn(self._llm, **config)
        return result

    async def generate_synthetic(
        self, domain: str, count: int = 20, quality_threshold: float = 0.6
    ) -> List[DataSample]:
        """Generate synthetic examples for a domain using the LLM."""
        if not self._llm:
            raise RuntimeError("LLM required for synthetic generation.")
        prompt = _SYNTHETIC_PROMPT.format(domain=domain, count=count)
        raw = await self._call_llm(prompt)
        samples = self._parse_samples(raw)
        scored = [s for s in samples if s.quality_score >= quality_threshold]
        logger.info(
            "Synthetic generation: %d generated, %d passed quality threshold (%.2f).",
            len(samples), len(scored), quality_threshold,
        )
        return scored

    # ── Refinement ──────────────────────────────────────────────────────

    async def refine_dataset(
        self, refiner_name: str, dataset: List[DataSample], config: Dict[str, Any]
    ) -> List[DataSample]:
        fn = self._refiners.get(refiner_name)
        if fn is None:
            raise ValueError(f"Refiner '{refiner_name}' not registered.")
        return await fn(dataset, self._llm, **config) if asyncio.iscoroutinefunction(fn) else fn(dataset, self._llm, **config)

    async def refine_sample(self, sample: DataSample) -> DataSample:
        """Use the LLM to improve a single data sample."""
        if not self._llm:
            return sample
        example_json = json.dumps({
            "instruction": sample.instruction,
            "input": sample.input,
            "output": sample.output,
        })
        prompt = _REFINE_PROMPT.format(example=example_json)
        raw = await self._call_llm(prompt)
        improved = self._parse_single(raw)
        if improved:
            sample.instruction = improved.get("instruction", sample.instruction)
            sample.input = improved.get("input", sample.input)
            sample.output = improved.get("output", sample.output)
            sample.quality_score = self._score_sample(sample)
        return sample

    # ── Deduplication ───────────────────────────────────────────────────

    def deduplicate(
        self, samples: List[DataSample], similarity_threshold: float = 0.85
    ) -> List[DataSample]:
        """Remove near-duplicate samples using Jaccard similarity on instruction tokens."""
        unique: List[DataSample] = []
        seen_tokens: List[set] = []

        for sample in samples:
            tokens = set(sample.instruction.lower().split())
            is_dup = any(
                self._jaccard(tokens, existing) >= similarity_threshold
                for existing in seen_tokens
            )
            if not is_dup:
                unique.append(sample)
                seen_tokens.append(tokens)

        removed = len(samples) - len(unique)
        logger.info("Deduplication: removed %d duplicates, kept %d.", removed, len(unique))
        return unique

    # ── Labelling ───────────────────────────────────────────────────────

    async def auto_label(
        self, samples: List[DataSample], task_type: str
    ) -> List[DataSample]:
        """Automatically label samples using the LLM."""
        if not self._llm:
            logger.warning("LLM required for auto-labelling. Returning unlabelled samples.")
            return samples

        labelled: List[DataSample] = []
        for sample in samples:
            prompt = _LABEL_PROMPT.format(
                text=f"{sample.instruction} {sample.input}"[:400],
                task_type=task_type,
            )
            try:
                raw = await self._call_llm(prompt)
                parsed = self._parse_json(raw)
                if parsed:
                    sample.label = parsed.get("label")
                    sample.metadata["label_confidence"] = parsed.get("confidence", 0.0)
            except Exception as exc:
                logger.warning("Auto-label failed for sample %s: %s", sample.id, exc)
            labelled.append(sample)
        return labelled

    # ── Quality Scoring ──────────────────────────────────────────────────

    def score_dataset(self, samples: List[DataSample]) -> List[DataSample]:
        """Compute quality scores for all samples in-place."""
        for sample in samples:
            sample.quality_score = self._score_sample(sample)
        return samples

    # ── Autonomous Loop ──────────────────────────────────────────────────

    async def run_autonomous_loop(
        self,
        domain: str,
        target_size: int = 100,
        max_iterations: int = 5,
        quality_threshold: float = 0.7,
    ) -> List[DataSample]:
        """
        Autonomous loop that generates, refines, and deduplicates data until
        target_size high-quality samples are collected.
        """
        logger.info("Starting autonomous data loop — domain=%s target=%d", domain, target_size)
        all_samples: List[DataSample] = []

        for iteration in range(1, max_iterations + 1):
            needed = target_size - len(all_samples)
            if needed <= 0:
                break
            logger.info("Iteration %d — generating %d samples.", iteration, min(needed, 20))

            batch = await self.generate_synthetic(
                domain=domain,
                count=min(needed, 20),
                quality_threshold=quality_threshold,
            )
            # Refine low-quality samples
            refined = []
            for s in batch:
                if s.quality_score < quality_threshold:
                    s = await self.refine_sample(s)
                refined.append(s)

            all_samples.extend(refined)
            all_samples = self.deduplicate(all_samples)
            logger.info("Iteration %d done — total valid: %d.", iteration, len(all_samples))

        logger.info("Autonomous loop complete — collected %d samples.", len(all_samples))
        return all_samples[:target_size]

    # ── Private helpers ──────────────────────────────────────────────────

    def _register_builtins(self) -> None:
        """Register built-in generators and refiners."""
        self._generators["synthetic"] = self._builtin_synthetic_generator
        self._refiners["llm"] = self._builtin_llm_refiner

    async def _builtin_synthetic_generator(
        self, llm: Any, domain: str = "general", count: int = 10, **kwargs
    ) -> List[DataSample]:
        return await self.generate_synthetic(domain, count)

    async def _builtin_llm_refiner(
        self, dataset: List[DataSample], llm: Any, **kwargs
    ) -> List[DataSample]:
        return [await self.refine_sample(s) for s in dataset]

    async def _call_llm(self, prompt: str) -> str:
        try:
            if hasattr(self._llm, "agenerate"):
                return await self._llm.agenerate(prompt)
            if hasattr(self._llm, "generate"):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._llm.generate, prompt)
            if callable(self._llm):
                result = self._llm(prompt)
                return await result if asyncio.iscoroutine(result) else result
        except Exception as exc:
            logger.error("DataFactory LLM call failed: %s", exc)
        return ""

    def _parse_samples(self, raw: str) -> List[DataSample]:
        if not raw:
            return []
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        try:
            items = json.loads(match.group())
            samples = []
            for item in items:
                if isinstance(item, dict):
                    s = DataSample(
                        instruction=item.get("instruction", ""),
                        input=item.get("input", ""),
                        output=item.get("output", ""),
                    )
                    s.quality_score = self._score_sample(s)
                    samples.append(s)
            return samples
        except json.JSONDecodeError:
            return []

    def _parse_single(self, raw: str) -> Optional[Dict]:
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict]:
        if not raw:
            return None
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _score_sample(sample: DataSample) -> float:
        score = 0.0
        if len(sample.instruction) > 10:
            score += 0.4
        if len(sample.output) > 20:
            score += 0.4
        if sample.input:
            score += 0.1
        if len(sample.output) > 100:
            score += 0.1
        return min(score, 1.0)

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        if not a and not b:
            return 1.0
        return len(a & b) / len(a | b)
