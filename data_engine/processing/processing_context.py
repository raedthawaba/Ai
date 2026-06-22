"""Processing Context — section 5.1.

A shared mutable context object that flows through the pipeline,
carrying articles, metrics, and metadata between stages.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.schemas.article import Article
from .processing_result import ProcessingError, ProcessingResult


@dataclass
class StageTrace:
    """Lightweight record of a single stage execution."""

    stage_name: str
    input_count: int
    output_count: int
    rejected_count: int
    duration_ms: float
    error_count: int


class ProcessingContext:
    """Shared state that flows through every pipeline stage.

    Parameters
    ----------
    articles:
        Initial list of articles entering the pipeline.
    source_id:
        Identifier of the data source feeding this run.
    run_id:
        Unique run identifier (auto-generated when omitted).
    config:
        Arbitrary runtime configuration passed to stages.
    """

    def __init__(
        self,
        articles: Optional[List[Article]] = None,
        source_id: str = "unknown",
        run_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.run_id: str = run_id or str(uuid.uuid4())
        self.source_id: str = source_id
        self.articles: List[Article] = list(articles or [])
        self.config: Dict[str, Any] = config or {}
        self.metadata: Dict[str, Any] = {}
        self.errors: List[ProcessingError] = []
        self.stage_traces: List[StageTrace] = []
        self._stage_results: List[ProcessingResult] = []
        self.created_at: datetime = datetime.now(tz=timezone.utc)
        self._pipeline_start: float = time.monotonic()
        self._aborted: bool = False

    # ------------------------------------------------------------------
    # Article management
    # ------------------------------------------------------------------

    @property
    def article_count(self) -> int:
        """Current number of articles in the context."""
        return len(self.articles)

    def replace_articles(self, articles: List[Article]) -> None:
        """Replace the current article list (called by each stage)."""
        self.articles = list(articles)

    def add_articles(self, articles: List[Article]) -> None:
        """Append additional articles to the current list."""
        self.articles.extend(articles)

    # ------------------------------------------------------------------
    # Error tracking
    # ------------------------------------------------------------------

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def record_error(
        self,
        stage: str,
        message: str,
        article_id: Optional[str] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        """Append a processing error to the context error list."""
        self.errors.append(
            ProcessingError(
                stage=stage,
                message=message,
                article_id=article_id,
                exc_type=type(exc).__name__ if exc else None,
            )
        )

    # ------------------------------------------------------------------
    # Stage tracing
    # ------------------------------------------------------------------

    def record_stage(self, result: ProcessingResult) -> None:
        """Record a completed stage result in the trace."""
        self._stage_results.append(result)
        self.stage_traces.append(
            StageTrace(
                stage_name=result.stage_name,
                input_count=result.input_count,
                output_count=result.output_count,
                rejected_count=result.rejected_count,
                duration_ms=result.duration_ms,
                error_count=result.error_count,
            )
        )
        self.errors.extend(result.errors)

    # ------------------------------------------------------------------
    # Abort mechanism
    # ------------------------------------------------------------------

    @property
    def is_aborted(self) -> bool:
        """True when a stage has requested pipeline abort."""
        return self._aborted

    def abort(self, reason: str) -> None:
        """Signal all subsequent stages to skip processing."""
        self._aborted = True
        self.metadata["abort_reason"] = reason

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Store an arbitrary metadata value."""
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a metadata value."""
        return self.metadata.get(key, default)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @property
    def elapsed_ms(self) -> float:
        """Wall-clock time since context creation in milliseconds."""
        return (time.monotonic() - self._pipeline_start) * 1000

    def summary(self) -> Dict[str, Any]:
        """Return a serialisable summary of the pipeline run."""
        return {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "article_count": self.article_count,
            "total_errors": len(self.errors),
            "aborted": self._aborted,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "stages": [
                {
                    "stage": t.stage_name,
                    "in": t.input_count,
                    "out": t.output_count,
                    "rejected": t.rejected_count,
                    "errors": t.error_count,
                    "ms": round(t.duration_ms, 2),
                }
                for t in self.stage_traces
            ],
        }
