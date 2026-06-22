"""Metadata Layer — Phase 6.5.

تتبّع شامل لبيانات وصفية كل مرحلة:
  - Article metadata
  - Chunk metadata
  - Embedding metadata
  - Pipeline stage metadata
"""
from .tracker import (
    MetadataTracker,
    ArticleMetadataRecord,
    ChunkMetadataRecord,
    EmbeddingMetaRecord,
    PipelineStageRecord,
)

__all__ = [
    "MetadataTracker",
    "ArticleMetadataRecord",
    "ChunkMetadataRecord",
    "EmbeddingMetaRecord",
    "PipelineStageRecord",
]
