"""Custom project exceptions."""

from __future__ import annotations

from typing import Any


class BaseProjectException(Exception):
    """Base exception for all project-specific errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationException(BaseProjectException):
    """Raised when data validation fails."""


class StorageException(BaseProjectException):
    """Raised when storage operations fail."""


class ChannelException(BaseProjectException):
    """Raised when channel-related operations fail."""


class PipelineException(BaseProjectException):
    """Raised when pipeline stages fail."""
