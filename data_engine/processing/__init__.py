"""Processing pipeline modules for the data engine."""

from .cleaning import TextCleaner, CleanerConfig, clean_text
from .filtering import ContentFilter, FilterConfig, FilterResult
from .enrichment import ContentEnricher, EnricherConfig
from .transformation import DataTransformer, TransformerConfig

# Phase 5 — Processing Architecture
from .base_processor import BaseProcessor, ChainedProcessor, PassthroughProcessor
from .processing_context import ProcessingContext, StageTrace
from .processing_result import ProcessingError, ProcessingResult

# Phase 2 — Unified Pipelines
from .cleaning import CleaningPipeline, CleaningPipelineConfig, CleaningMetrics
from .filtering import (
    PIIFilter, PIIFilterConfig,
    FilteringPipeline, FilteringPipelineConfig, FilteringMetrics,
)
from .enrichment import (
    TopicClassifier, TopicClassifierConfig,
    SentimentAnalyzer, SentimentConfig,
    EnrichmentPipeline, EnrichmentPipelineConfig,
)
from .transformation import (
    MarkdownConverter, MarkdownConverterConfig,
    TransformationPipeline, TransformationPipelineConfig,
)

__all__ = [
    # Phase 4
    "TextCleaner",
    "CleanerConfig",
    "clean_text",
    "ContentFilter",
    "FilterConfig",
    "FilterResult",
    "ContentEnricher",
    "EnricherConfig",
    "DataTransformer",
    "TransformerConfig",
    # Phase 5
    "BaseProcessor",
    "ChainedProcessor",
    "PassthroughProcessor",
    "ProcessingContext",
    "ProcessingError",
    "ProcessingResult",
    "StageTrace",
    # Phase 2 — Unified Pipelines
    "CleaningPipeline",
    "CleaningPipelineConfig",
    "CleaningMetrics",
    "PIIFilter",
    "PIIFilterConfig",
    "FilteringPipeline",
    "FilteringPipelineConfig",
    "FilteringMetrics",
    "TopicClassifier",
    "TopicClassifierConfig",
    "SentimentAnalyzer",
    "SentimentConfig",
    "EnrichmentPipeline",
    "EnrichmentPipelineConfig",
    "MarkdownConverter",
    "MarkdownConverterConfig",
    "TransformationPipeline",
    "TransformationPipelineConfig",
]
