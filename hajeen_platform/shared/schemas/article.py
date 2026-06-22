"""Shared article schema definitions — Phase 2 enhanced."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from shared.utils.datetime_utils import utc_now
from shared.utils.validators import validate_language_code


# ─────────────────────────────────────────────────────────────────────────────
# Processing State (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

class ProcessingState(str, Enum):
    """حالة معالجة المقال عبر pipeline."""
    RAW = "raw"                 # لم تُطبَّق أي معالجة
    CLEANED = "cleaned"         # مرّ بـ CleaningPipeline
    FILTERED = "filtered"       # مرّ بـ FilteringPipeline
    ENRICHED = "enriched"       # مرّ بـ EnrichmentPipeline
    TRANSFORMED = "transformed" # مرّ بـ TransformationPipeline
    FAILED = "failed"           # فشل في إحدى المراحل


def generate_article_id(prefix: str = "art") -> str:
    """توليد معرّف فريد للمقال.

    Parameters
    ----------
    prefix:
        بادئة المعرّف (الافتراضي ``"art"``).

    Returns
    -------
    معرّف فريد من الشكل ``art_<uuid8>``.
    """
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class ArticleEntity(BaseModel):
    """Named entity extracted from article content."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="Entity text")
    label: str = Field(..., min_length=1, description="Entity label")
    start_char: int = Field(..., ge=0, description="Start offset in the content")
    end_char: int = Field(..., ge=0, description="End offset in the content")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")


class ArticleMetadata(BaseModel):
    """Metadata accompanying an article."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, description="Origin channel identifier")
    author: str | None = Field(default=None, description="Optional author name")
    language: str = Field(default="ar", description="ISO 639-1 language code")
    tags: list[str] = Field(default_factory=list, description="Tag list")
    entities: list[ArticleEntity] = Field(default_factory=list, description="Extracted entities")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Validate and normalize the language code."""
        normalized = value.strip().lower()
        if not validate_language_code(normalized):
            raise ValueError("Invalid language code.")
        return normalized


class Article(BaseModel):
    """Normalized article representation used across the data engine."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "art_123",
                "title": "عنوان المقال",
                "content": "محتوى المقال التفصيلي...",
                "url": "https://example.com/article",
                "published_at": "2024-05-20T10:00:00Z",
                "metadata": {"source_id": "ch_news_1", "language": "ar"},
            }
        },
    )

    id: str = Field(..., min_length=1, description="Unique article identifier")
    title: str = Field(..., min_length=1, description="Article title")
    content: str = Field(..., min_length=1, description="Article body text")
    url: HttpUrl = Field(..., description="Canonical article URL")
    published_at: datetime = Field(..., description="Original publication timestamp")
    extracted_at: datetime = Field(default_factory=utc_now, description="Extraction timestamp in UTC")
    summary: str | None = Field(default=None, description="Optional summary")
    metadata: ArticleMetadata = Field(..., description="Structured article metadata")

    # Phase 2 — معالجة الحالة
    processing_state: ProcessingState = Field(
        default=ProcessingState.RAW,
        description="حالة المعالجة الحالية للمقال",
    )

    @field_validator("id", "title", "content")
    @classmethod
    def strip_non_empty_strings(cls, value: str) -> str:
        """Trim required text fields and reject blank values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized

    # ─── Phase 2 helpers ──────────────────────────────────────────────────

    def content_hash(self) -> str:
        """SHA-256 لمحتوى المقال (للكشف عن التكرار).

        Returns
        -------
        سلسلة hex بطول 64 حرف.
        """
        key = (self.title.strip().lower() + self.content.strip()[:1000].lower())
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def short_hash(self) -> str:
        """أول 16 حرف من content_hash (للعرض)."""
        return self.content_hash()[:16]

    def to_dict(self, *, exclude_content: bool = False) -> dict[str, Any]:
        """تحويل المقال إلى dict.

        Parameters
        ----------
        exclude_content:
            إذا True → حذف حقل ``content`` من المخرجات.

        Returns
        -------
        dict قابل للتسلسل.
        """
        data = self.model_dump(mode="json")
        if exclude_content:
            data.pop("content", None)
        return data

    def to_json(self, *, indent: Optional[int] = None, **kwargs: Any) -> str:
        """تحويل المقال إلى JSON string.

        Parameters
        ----------
        indent:
            مسافة البادئة (None = compact).
        **kwargs:
            معاملات إضافية لـ json.dumps.

        Returns
        -------
        JSON string.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, **kwargs)

    def to_jsonl(self) -> str:
        """سطر JSONL واحد (بدون newline في النهاية).

        Returns
        -------
        JSON في سطر واحد.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def create(
        cls,
        *,
        title: str,
        content: str,
        url: str,
        published_at: datetime,
        source_id: str,
        language: str = "ar",
        id: Optional[str] = None,
        **kwargs: Any,
    ) -> "Article":
        """Factory method لإنشاء Article بمعرّف تلقائي.

        Parameters
        ----------
        title, content, url, published_at, source_id:
            الحقول الإلزامية.
        language:
            اللغة (الافتراضي ``"ar"``).
        id:
            معرّف مخصص؛ إذا None → يُولَّد تلقائياً.

        Returns
        -------
        Article جديد.
        """
        from shared.schemas.article import ArticleMetadata
        return cls(
            id=id or generate_article_id(),
            title=title,
            content=content,
            url=url,  # type: ignore[arg-type]
            published_at=published_at,
            metadata=ArticleMetadata(source_id=source_id, language=language),
            **kwargs,
        )
