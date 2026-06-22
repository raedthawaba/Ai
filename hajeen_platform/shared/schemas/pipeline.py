"""Shared pipeline schema definitions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineStageStatus(str, Enum):
    """Execution status for an individual pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStage(BaseModel):
    """Configuration and execution details for a pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Stage name")
    status: PipelineStageStatus = Field(default=PipelineStageStatus.PENDING, description="Stage status")
    started_at: datetime | None = Field(default=None, description="Stage start time")
    finished_at: datetime | None = Field(default=None, description="Stage finish time")
    config: dict[str, Any] = Field(default_factory=dict, description="Stage configuration")
    error: str | None = Field(default=None, description="Error message when failed")


class PipelineConfig(BaseModel):
    """Pipeline definition used by channels and orchestrators."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Unique pipeline identifier")
    name: str = Field(..., min_length=1, description="Pipeline name")
    stages: list[str] = Field(..., min_length=1, description="Ordered stage names")
    config: dict[str, Any] = Field(default_factory=dict, description="Additional pipeline configuration")

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, value: list[str]) -> list[str]:
        """Ensure stages are non-empty strings."""
        normalized = [stage.strip() for stage in value if stage.strip()]
        if not normalized:
            raise ValueError("Pipeline must contain at least one stage.")
        return normalized


class PipelineResult(BaseModel):
    """Result metadata produced by pipeline execution."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    pipeline_id: str = Field(..., min_length=1, description="Pipeline identifier")
    target_id: str = Field(..., min_length=1, description="Processed target identifier")
    status: PipelineStageStatus = Field(..., description="Overall pipeline status")
    stages_executed: list[PipelineStage] = Field(default_factory=list, description="Executed stages")
    started_at: datetime = Field(..., description="Pipeline start time")
    finished_at: datetime | None = Field(default=None, description="Pipeline finish time")
    total_duration: float | None = Field(default=None, ge=0.0, description="Pipeline duration in seconds")
