"""Processing Result — section 5.1.

Represents the outcome of a single processing step or an entire pipeline run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.schemas.article import Article


@dataclass
class ProcessingError:
    """A single error captured during processing."""

    stage: str
    message: str
    article_id: Optional[str] = None
    exc_type: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.stage}]"]
        if self.article_id:
            parts.append(f"article={self.article_id}")
        parts.append(self.message)
        return " ".join(parts)


@dataclass
class ProcessingResult:
    """Immutable summary of what happened during a processing pass.

    Parameters
    ----------
    stage_name:
        Identifier of the processor or pipeline that produced this result.
    input_count:
        Number of articles that entered the stage.
    output_articles:
        Articles that passed / were produced by the stage.
    rejected_count:
        Articles discarded at this stage.
    errors:
        Non-fatal errors captured during processing.
    metadata:
        Arbitrary key-value pairs attached by the stage.
    duration_ms:
        Wall-clock processing time in milliseconds.
    """

    stage_name: str
    input_count: int = 0
    output_articles: List[Article] = field(default_factory=list)
    rejected_count: int = 0
    errors: List[ProcessingError] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def output_count(self) -> int:
        """Number of articles in the output."""
        return len(self.output_articles)

    @property
    def success(self) -> bool:
        """True when no fatal errors were recorded and output is non-empty
        whenever there was input."""
        return not self.errors or self.output_count > 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def pass_rate(self) -> float:
        """Fraction of input articles that made it to output (0–1)."""
        if self.input_count == 0:
            return 1.0
        return self.output_count / self.input_count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def add_error(
        self,
        stage: str,
        message: str,
        article_id: Optional[str] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        """Append a :class:`ProcessingError` to the error list."""
        self.errors.append(
            ProcessingError(
                stage=stage,
                message=message,
                article_id=article_id,
                exc_type=type(exc).__name__ if exc else None,
            )
        )

    def summary(self) -> Dict[str, Any]:
        """Return a serialisable summary dict."""
        return {
            "stage": self.stage_name,
            "input": self.input_count,
            "output": self.output_count,
            "rejected": self.rejected_count,
            "errors": self.error_count,
            "pass_rate": round(self.pass_rate, 4),
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
        }

    @classmethod
    def empty(cls, stage_name: str) -> "ProcessingResult":
        """Return a zero-state result for *stage_name*."""
        return cls(stage_name=stage_name)

    @classmethod
    def from_articles(
        cls,
        stage_name: str,
        input_count: int,
        output_articles: List[Article],
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ProcessingResult":
        """Convenience constructor for a successful stage pass."""
        rejected = max(0, input_count - len(output_articles))
        return cls(
            stage_name=stage_name,
            input_count=input_count,
            output_articles=output_articles,
            rejected_count=rejected,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
