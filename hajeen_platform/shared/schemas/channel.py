"""Shared channel schema definitions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from shared.utils.datetime_utils import utc_now
from shared.utils.validators import validate_cron_expression


class ChannelStatus(str, Enum):
    """Lifecycle status for a channel."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    ERROR = "error"
    PAUSED = "paused"


class ScheduleConfig(BaseModel):
    """Scheduling details for channel execution."""

    model_config = ConfigDict(extra="forbid")

    cron: str = Field(..., description="Cron expression for scheduling")
    enabled: bool = Field(default=True, description="Whether scheduling is enabled")
    timezone: str = Field(default="UTC", description="Schedule timezone")

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        normalized = value.strip()
        if not validate_cron_expression(normalized):
            raise ValueError("Invalid cron expression.")
        return normalized


class SourceConfig(BaseModel):
    """Source configuration for a channel."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl = Field(..., description="Source endpoint URL")
    type: str = Field(..., min_length=1, description="Source type such as rss, api, or demo")
    params: dict[str, Any] = Field(default_factory=dict, description="Additional source parameters")

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().lower()


class ChannelStats(BaseModel):
    """Runtime statistics for a channel."""

    model_config = ConfigDict(extra="allow")

    total_runs: int = Field(default=0, description="Total pipeline executions")
    successful_runs: int = Field(default=0, description="Successful executions")
    failed_runs: int = Field(default=0, description="Failed executions")
    total_fetched: int = Field(default=0, description="Total articles fetched")
    total_processed: int = Field(default=0, description="Total articles processed")
    total_stored: int = Field(default=0, description="Total articles stored")
    last_run_at: Optional[datetime] = Field(default=None, description="Last run timestamp")
    last_run_status: Optional[str] = Field(default=None, description="Last run status")
    last_error: Optional[str] = Field(default=None, description="Last error message")
    avg_duration_ms: float = Field(default=0.0, description="Average run duration in ms")


class ChannelConfig(BaseModel):
    """Primary configuration model used to instantiate channels."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: str = Field(..., min_length=1, description="Unique channel identifier")
    name: str = Field(..., min_length=1, description="Human-readable channel name")
    description: str | None = Field(default=None, description="Optional channel description")
    status: ChannelStatus = Field(default=ChannelStatus.DRAFT, description="Current channel status")
    source: SourceConfig = Field(..., description="Channel source configuration")
    schedule: ScheduleConfig | None = Field(default=None, description="Optional schedule configuration")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary channel metadata")
    stats: ChannelStats = Field(default_factory=ChannelStats, description="Runtime statistics")
    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp in UTC")

    @field_validator("id", "name")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized
