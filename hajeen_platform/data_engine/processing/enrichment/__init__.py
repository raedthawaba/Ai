"""Enrichment processors — sections 4.12, 5.9, 5.10, 5.11, Phase 2."""
from .content_enricher import ContentEnricher, EnricherConfig
from .keyword_extractor import KeywordExtractor, KeywordExtractorConfig
from .entity_extractor import EntityExtractor, EntityExtractorConfig
from .summarizer import Summarizer, SummarizerConfig

# Phase 2 — topic, sentiment, unified pipeline
from .topic_classifier import (
    TopicClassifier,
    TopicClassifierConfig,
    ClassificationResult,
    TopicScore,
)
from .sentiment_analyzer import (
    SentimentAnalyzer,
    SentimentConfig,
    SentimentResult,
)
from .enrichment_pipeline import (
    EnrichmentPipeline,
    EnrichmentPipelineConfig,
    EnrichmentMetrics,
    ArticleEnrichmentMetrics,
)

__all__ = [
    "ContentEnricher", "EnricherConfig",
    "KeywordExtractor", "KeywordExtractorConfig",
    "EntityExtractor", "EntityExtractorConfig",
    "Summarizer", "SummarizerConfig",
    # Phase 2
    "TopicClassifier", "TopicClassifierConfig", "ClassificationResult", "TopicScore",
    "SentimentAnalyzer", "SentimentConfig", "SentimentResult",
    "EnrichmentPipeline", "EnrichmentPipelineConfig",
    "EnrichmentMetrics", "ArticleEnrichmentMetrics",
]
