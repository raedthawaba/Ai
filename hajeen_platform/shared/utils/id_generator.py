"""Identifier generation helpers."""

from __future__ import annotations

import hashlib
import uuid


def generate_id(prefix: str = "") -> str:
    """Generate a short unique identifier with an optional prefix."""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}{uid}" if prefix else uid


def generate_channel_id() -> str:
    """Generate a unique channel identifier."""
    return generate_id("ch_")


def generate_article_id(url: str) -> str:
    """Generate a stable article identifier from a source URL."""
    hash_object = hashlib.md5(url.encode("utf-8"), usedforsecurity=False)
    return f"art_{hash_object.hexdigest()[:16]}"
