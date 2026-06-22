"""Response models for the data ingestion engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field

from shared.utils.datetime_utils import utc_now


class ResponseMetadata(BaseModel):
    """Metadata about an HTTP response."""
    url: str
    status_code: int
    headers: Dict[str, str]
    elapsed_time: float  # In seconds
    content_type: Optional[str] = None
    encoding: Optional[str] = None


class FetchResponse(BaseModel):
    """Represents a successful data fetch result."""
    content: Union[str, bytes]
    metadata: ResponseMetadata
    timestamp: datetime = Field(default_factory=utc_now)

    @property
    def is_json(self) -> bool:
        """Check if the content is likely JSON based on content-type."""
        ct = self.metadata.content_type or ""
        return "application/json" in ct.lower()

    def json(self) -> Any:
        """Parse content as JSON if possible."""
        import json
        if isinstance(self.content, bytes):
            return json.loads(self.content.decode(self.metadata.encoding or "utf-8"))
        return json.loads(self.content)


class FetchError(BaseModel):
    """Represents an error during the fetch process."""
    url: str
    error_type: str
    message: str
    status_code: Optional[int] = None
    timestamp: datetime = Field(default_factory=utc_now)
    retry_count: int = 0
