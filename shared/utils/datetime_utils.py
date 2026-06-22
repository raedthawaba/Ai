"""Datetime helpers used across the project."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def iso_timestamp(dt: datetime | None = None) -> str:
    """Return a UTC ISO 8601 timestamp string.

    If *dt* is omitted, the current UTC time is used.
    """
    value = dt.astimezone(timezone.utc) if dt is not None else utc_now()
    return value.isoformat()
