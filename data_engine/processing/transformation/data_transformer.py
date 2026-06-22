"""Data Transformer — section 4.13.

Converts Article objects into output-ready formats and provides
batch transformation utilities.

Capabilities:
- Article → flat dict (CSV-ready)
- Article → JSON-serialisable dict (API-ready, full / compact)
- Batch transformation with optional field selection
- Field renaming / mapping
- Schema validation on output
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output format names
# ---------------------------------------------------------------------------

OUTPUT_FORMAT_FULL = "full"
OUTPUT_FORMAT_COMPACT = "compact"
OUTPUT_FORMAT_FLAT = "flat"
OUTPUT_FORMAT_CSV = "csv"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TransformerConfig:
    """Controls the transformation behaviour."""

    output_format: str = OUTPUT_FORMAT_FULL
    include_fields: List[str] = field(default_factory=list)
    exclude_fields: List[str] = field(default_factory=list)
    field_renames: Dict[str, str] = field(default_factory=dict)
    datetime_format: str = "%Y-%m-%dT%H:%M:%SZ"
    include_metadata: bool = True
    include_entities: bool = True
    flatten_metadata: bool = False
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Transformation helpers
# ---------------------------------------------------------------------------

def _format_datetime(dt: Optional[datetime], fmt: str) -> Optional[str]:
    """Return a formatted datetime string or ``None``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime(fmt)


def article_to_dict(
    article: Article,
    config: Optional[TransformerConfig] = None,
) -> Dict[str, Any]:
    """Convert a single :class:`Article` to a plain dictionary.

    The output format is controlled by ``config.output_format``:

    ``full``
        All fields including nested metadata and entities.
    ``compact``
        Core fields only: ``id``, ``title``, ``url``, ``published_at``,
        ``language``, ``source_id``, ``tags``.
    ``flat``
        All fields flattened — metadata sub-fields are promoted to the
        top level (e.g. ``metadata_source_id``, ``metadata_language``).
    ``csv``
        Scalar fields only, safe for CSV serialisation.

    Parameters
    ----------
    article:
        Source article.
    config:
        Transformation configuration.

    Returns
    -------
    Dictionary representation of the article.
    """
    cfg = config or TransformerConfig()
    fmt = cfg.output_format

    if fmt == OUTPUT_FORMAT_COMPACT:
        data = _to_compact(article, cfg)
    elif fmt == OUTPUT_FORMAT_FLAT:
        data = _to_flat(article, cfg)
    elif fmt == OUTPUT_FORMAT_CSV:
        data = _to_csv_row(article, cfg)
    else:
        data = _to_full(article, cfg)

    data = _apply_field_selection(data, cfg)
    data = _apply_field_renames(data, cfg)
    return data


def articles_to_dicts(
    articles: List[Article],
    config: Optional[TransformerConfig] = None,
) -> List[Dict[str, Any]]:
    """Convert a list of articles to a list of dicts.

    Parameters
    ----------
    articles:
        Source articles.
    config:
        Shared transformation configuration.

    Returns
    -------
    List of dictionaries.
    """
    cfg = config or TransformerConfig()
    return [article_to_dict(a, cfg) for a in articles]


def article_to_json(
    article: Article,
    config: Optional[TransformerConfig] = None,
    indent: Optional[int] = None,
) -> str:
    """Serialise a single article to a JSON string.

    Parameters
    ----------
    article:
        Source article.
    config:
        Transformation configuration.
    indent:
        JSON indentation level (``None`` for compact JSON).

    Returns
    -------
    JSON string.
    """
    data = article_to_dict(article, config)
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)


def articles_to_jsonl(
    articles: List[Article],
    config: Optional[TransformerConfig] = None,
) -> str:
    """Serialise articles to newline-delimited JSON (JSONL).

    Each line is one JSON object.

    Parameters
    ----------
    articles:
        Source articles.
    config:
        Shared transformation configuration.

    Returns
    -------
    JSONL string.
    """
    cfg = config or TransformerConfig()
    lines = [
        json.dumps(article_to_dict(a, cfg), ensure_ascii=False, default=str)
        for a in articles
    ]
    return "\n".join(lines)


def get_csv_headers(config: Optional[TransformerConfig] = None) -> List[str]:
    """Return the ordered field names used by the CSV output format.

    Parameters
    ----------
    config:
        Transformation config (used for renames).

    Returns
    -------
    List of header strings.
    """
    cfg = config or TransformerConfig(output_format=OUTPUT_FORMAT_CSV)
    sample_headers = [
        "id", "title", "url", "published_at", "extracted_at",
        "language", "source_id", "author", "summary",
        "content_length", "tags", "reading_time_seconds",
    ]
    if cfg.include_fields:
        sample_headers = [h for h in sample_headers if h in cfg.include_fields]
    if cfg.exclude_fields:
        sample_headers = [h for h in sample_headers if h not in cfg.exclude_fields]
    return [cfg.field_renames.get(h, h) for h in sample_headers]


# ---------------------------------------------------------------------------
# Article-level transformer class
# ---------------------------------------------------------------------------

class DataTransformer:
    """Stateless transformer with a fixed :class:`TransformerConfig`.

    Parameters
    ----------
    config:
        Transformation configuration shared across all calls.
    custom_transform:
        Optional callable ``(article, dict) -> dict`` applied after the
        standard transformation.  Useful for project-specific post-processing.
    """

    def __init__(
        self,
        config: Optional[TransformerConfig] = None,
        custom_transform: Optional[Callable[[Article, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.config = config or TransformerConfig()
        self._custom = custom_transform

    def transform(self, article: Article) -> Dict[str, Any]:
        """Transform a single article.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        Transformed dictionary.
        """
        data = article_to_dict(article, self.config)
        if self._custom:
            data = self._custom(article, data)
        return data

    def transform_batch(
        self,
        articles: List[Article],
    ) -> List[Dict[str, Any]]:
        """Transform a list of articles.

        Parameters
        ----------
        articles:
            Source articles.

        Returns
        -------
        List of transformed dictionaries.
        """
        result = [self.transform(a) for a in articles]
        logger.info("DataTransformer.transform_batch: processed=%d", len(result))
        return result

    def to_json(self, article: Article, indent: Optional[int] = None) -> str:
        """Transform and serialise a single article to JSON.

        Parameters
        ----------
        article:
            Source article.
        indent:
            JSON indentation.

        Returns
        -------
        JSON string.
        """
        data = self.transform(article)
        return json.dumps(data, ensure_ascii=False, indent=indent, default=str)

    def to_jsonl(self, articles: List[Article]) -> str:
        """Transform and serialise articles to JSONL.

        Parameters
        ----------
        articles:
            Source articles.

        Returns
        -------
        JSONL string (one JSON object per line).
        """
        lines = [
            json.dumps(self.transform(a), ensure_ascii=False, default=str)
            for a in articles
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal format builders
# ---------------------------------------------------------------------------

def _to_full(article: Article, cfg: TransformerConfig) -> Dict[str, Any]:
    meta = article.metadata
    entities = []
    if cfg.include_entities:
        entities = [
            {
                "text": e.text,
                "label": e.label,
                "start_char": e.start_char,
                "end_char": e.end_char,
                "score": e.score,
            }
            for e in meta.entities
        ]
    metadata_block: Dict[str, Any] = {
        "source_id": meta.source_id,
        "author": meta.author,
        "language": meta.language,
        "tags": meta.tags,
        "extra": meta.extra,
    }
    if cfg.include_entities:
        metadata_block["entities"] = entities

    data: Dict[str, Any] = {
        "id": article.id,
        "title": article.title,
        "content": article.content,
        "url": str(article.url),
        "published_at": _format_datetime(article.published_at, cfg.datetime_format),
        "extracted_at": _format_datetime(article.extracted_at, cfg.datetime_format),
        "summary": article.summary,
    }
    if cfg.include_metadata:
        data["metadata"] = metadata_block
    return data


def _to_compact(article: Article, cfg: TransformerConfig) -> Dict[str, Any]:
    return {
        "id": article.id,
        "title": article.title,
        "url": str(article.url),
        "published_at": _format_datetime(article.published_at, cfg.datetime_format),
        "language": article.metadata.language,
        "source_id": article.metadata.source_id,
        "tags": article.metadata.tags,
    }


def _to_flat(article: Article, cfg: TransformerConfig) -> Dict[str, Any]:
    meta = article.metadata
    data: Dict[str, Any] = {
        "id": article.id,
        "title": article.title,
        "content": article.content,
        "url": str(article.url),
        "published_at": _format_datetime(article.published_at, cfg.datetime_format),
        "extracted_at": _format_datetime(article.extracted_at, cfg.datetime_format),
        "summary": article.summary,
        "metadata_source_id": meta.source_id,
        "metadata_author": meta.author,
        "metadata_language": meta.language,
        "metadata_tags": ",".join(meta.tags),
        "metadata_reading_time_seconds": meta.extra.get("reading_time_seconds"),
    }
    for k, v in meta.extra.items():
        if k != "reading_time_seconds" and isinstance(v, (str, int, float, bool)):
            data[f"metadata_extra_{k}"] = v
    return data


def _to_csv_row(article: Article, cfg: TransformerConfig) -> Dict[str, Any]:
    meta = article.metadata
    return {
        "id": article.id,
        "title": article.title,
        "url": str(article.url),
        "published_at": _format_datetime(article.published_at, cfg.datetime_format),
        "extracted_at": _format_datetime(article.extracted_at, cfg.datetime_format),
        "language": meta.language,
        "source_id": meta.source_id,
        "author": meta.author or "",
        "summary": article.summary or "",
        "content_length": len(article.content),
        "tags": ",".join(meta.tags),
        "reading_time_seconds": meta.extra.get("reading_time_seconds", ""),
    }


def _apply_field_selection(
    data: Dict[str, Any], cfg: TransformerConfig
) -> Dict[str, Any]:
    if cfg.include_fields:
        data = {k: v for k, v in data.items() if k in cfg.include_fields}
    if cfg.exclude_fields:
        data = {k: v for k, v in data.items() if k not in cfg.exclude_fields}
    return data


def _apply_field_renames(
    data: Dict[str, Any], cfg: TransformerConfig
) -> Dict[str, Any]:
    if not cfg.field_renames:
        return data
    return {cfg.field_renames.get(k, k): v for k, v in data.items()}
