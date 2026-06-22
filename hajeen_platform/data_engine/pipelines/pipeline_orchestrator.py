"""Pipeline Orchestrator — section 5.15.

Concrete orchestrator that builds and runs the full processing pipeline:

    Fetch → Clean → Filter → Enrich → Transform → Store

Each stage is individually configurable. The orchestrator also collects
pipeline-level metrics (stage durations, article counts, rejection rates).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable

from shared.schemas.article import Article
from data_engine.processing.processing_context import ProcessingContext
from data_engine.pipelines.base_pipeline import BasePipeline
from data_engine.pipelines.stages import (
    FetchStage, CleanStage, FilterStage,
    EnrichStage, TransformStage, StoreStage,
)
from data_engine.processing.cleaning.text_normalizer import NormalizerConfig
from data_engine.processing.filtering.deduplicator import DeduplicatorConfig
from data_engine.processing.filtering.language_filter import LanguageFilterConfig
from data_engine.processing.filtering.quality_scorer import QualityScorerConfig
from data_engine.processing.filtering.spam_detector import SpamDetectorConfig
from data_engine.processing.filtering.policy_filter import PolicyFilterConfig
from data_engine.processing.enrichment.content_enricher import EnricherConfig
from data_engine.processing.enrichment.keyword_extractor import KeywordExtractorConfig
from data_engine.processing.enrichment.entity_extractor import EntityExtractorConfig
from data_engine.processing.enrichment.summarizer import SummarizerConfig
from data_engine.processing.transformation.chunker import ChunkerConfig
from data_engine.processing.transformation.tokenizer_wrapper import TokenizerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class PipelineMetrics:
    """Simple per-run metrics collected by the orchestrator."""

    pipeline_name: str
    run_id: str
    input_count: int = 0
    output_count: int = 0
    total_duration_ms: float = 0.0
    stage_metrics: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        if self.input_count == 0:
            return 0.0
        return 1.0 - (self.output_count / self.input_count)

    def summary(self) -> Dict[str, Any]:
        return {
            "pipeline": self.pipeline_name,
            "run_id": self.run_id,
            "input": self.input_count,
            "output": self.output_count,
            "rejection_rate": round(self.rejection_rate, 4),
            "duration_ms": round(self.total_duration_ms, 2),
            "errors": len(self.errors),
            "stages": self.stage_metrics,
        }


# ---------------------------------------------------------------------------
# PipelineOrchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator(BasePipeline):
    """Builds and runs the full Fetch → Clean → Filter → Enrich → Transform → Store pipeline.

    Parameters
    ----------
    name:
        Pipeline name used in logs and metrics.
    source_id:
        Identifier of the data source (stored in context).
    fetch_fn:
        Optional async callable returning a list of articles.
        When provided, it replaces pre-loaded articles in the context.
    storage_manager:
        Optional storage manager for the store stage.
    policy_config_path:
        Path to ``filters.yaml`` for the policy filter.
    allowed_languages:
        Languages to allow (default: ["ar", "en"]).
    """

    def __init__(
        self,
        name: str = "default_pipeline",
        source_id: str = "unknown",
        fetch_fn: Optional[Callable[[], Awaitable[List[Article]]]] = None,
        storage_manager=None,
        policy_config_path: Optional[str] = None,
        allowed_languages: Optional[List[str]] = None,
        # Per-stage configs
        normalizer_config: Optional[NormalizerConfig] = None,
        dedup_config: Optional[DeduplicatorConfig] = None,
        lang_config: Optional[LanguageFilterConfig] = None,
        quality_config: Optional[QualityScorerConfig] = None,
        spam_config: Optional[SpamDetectorConfig] = None,
        policy_config: Optional[PolicyFilterConfig] = None,
        enricher_config: Optional[EnricherConfig] = None,
        kw_config: Optional[KeywordExtractorConfig] = None,
        entity_config: Optional[EntityExtractorConfig] = None,
        summarizer_config: Optional[SummarizerConfig] = None,
        chunker_config: Optional[ChunkerConfig] = None,
        tokenizer_config: Optional[TokenizerConfig] = None,
    ) -> None:
        super().__init__(name=name)
        self.source_id = source_id
        self._last_metrics: Optional[PipelineMetrics] = None

        # Build and register stages
        self.add_stage(FetchStage(fetch_fn=fetch_fn))

        self.add_stage(CleanStage(normalizer_config=normalizer_config))

        self.add_stage(
            FilterStage(
                dedup_config=dedup_config,
                lang_config=lang_config,
                quality_config=quality_config,
                spam_config=spam_config,
                policy_config=policy_config,
                allowed_languages=allowed_languages,
                policy_config_path=policy_config_path,
            )
        )

        self.add_stage(
            EnrichStage(
                enricher_config=enricher_config,
                kw_config=kw_config,
                entity_config=entity_config,
                summarizer_config=summarizer_config,
            )
        )

        self.add_stage(TransformStage(chunker_config=chunker_config, tokenizer_config=tokenizer_config))

        self.add_stage(StoreStage(storage_manager=storage_manager))

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self,
        articles: Optional[List[Article]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ProcessingContext:
        """Execute the full pipeline.

        Parameters
        ----------
        articles:
            Pre-fetched articles.  When provided, they seed the context
            (the fetch stage passes them through unchanged unless a
            ``fetch_fn`` was supplied at construction time).
        config:
            Runtime configuration dict merged into the context.

        Returns
        -------
        Final :class:`ProcessingContext`.
        """
        context = ProcessingContext(
            articles=articles or [],
            source_id=self.source_id,
            config=config or {},
        )
        input_count = context.article_count
        start = time.monotonic()

        logger.info(
            "%s: starting run_id=%s input=%d",
            self.name,
            context.run_id,
            input_count,
        )

        await self._execute_stages(context)

        duration_ms = (time.monotonic() - start) * 1000

        metrics = PipelineMetrics(
            pipeline_name=self.name,
            run_id=context.run_id,
            input_count=input_count,
            output_count=context.article_count,
            total_duration_ms=duration_ms,
            stage_metrics=[t.__dict__ for t in context.stage_traces],
            errors=[str(e) for e in context.errors],
        )
        self._last_metrics = metrics

        logger.info(
            "%s: done — in=%d out=%d rejection=%.1f%% elapsed=%.1fms",
            self.name,
            input_count,
            context.article_count,
            metrics.rejection_rate * 100,
            duration_ms,
        )
        return context

    @property
    def last_metrics(self) -> Optional[PipelineMetrics]:
        """Return the metrics from the most recent run."""
        return self._last_metrics
