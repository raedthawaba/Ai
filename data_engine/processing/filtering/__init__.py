"""Content filtering module."""

from .content_filter import (
    ContentFilter,
    FilterConfig,
    FilterResult,
    detect_language,
    is_arabic,
    compute_quality_score,
)

# Phase 5 — new filtering modules
from .deduplicator import (
    Deduplicator,
    DeduplicatorConfig,
    DedupResult,
    content_hash,
    url_hash,
    similarity_score,
)

from .language_filter import (
    LanguageFilter,
    LanguageFilterConfig,
    LanguageFilterResult,
    LanguageDetectionResult,
    detect_language as detect_language_v2,
)

from .quality_scorer import (
    QualityScorer,
    QualityScorerConfig,
    QualityScore,
    score_content_length,
    score_word_count,
    score_link_density,
    score_repetition,
    score_readability,
    score_metadata,
)

from .spam_detector import (
    SpamDetector,
    SpamDetectorConfig,
    SpamResult,
    check_keyword_spam,
    check_repeated_links,
    check_repeated_phrases,
    check_caps_ratio,
    check_punct_density,
)

# Phase 2 — PII filter + unified pipeline
from .pii_filter import (
    PIIFilter,
    PIIFilterConfig,
    PIIRedactionResult,
    PIIMatch,
)
from .filtering_pipeline import (
    FilteringPipeline,
    FilteringPipelineConfig,
    FilteringMetrics,
    ArticleFilterResult,
)

__all__ = [
    # Phase 4
    "ContentFilter",
    "FilterConfig",
    "FilterResult",
    "detect_language",
    "is_arabic",
    "compute_quality_score",
    # Phase 5 — deduplicator
    "Deduplicator",
    "DeduplicatorConfig",
    "DedupResult",
    "content_hash",
    "url_hash",
    "similarity_score",
    # Phase 5 — language_filter
    "LanguageFilter",
    "LanguageFilterConfig",
    "LanguageFilterResult",
    "LanguageDetectionResult",
    "detect_language_v2",
    # Phase 5 — quality_scorer
    "QualityScorer",
    "QualityScorerConfig",
    "QualityScore",
    "score_content_length",
    "score_word_count",
    "score_link_density",
    "score_repetition",
    "score_readability",
    "score_metadata",
    # Phase 5 — spam_detector
    "SpamDetector",
    "SpamDetectorConfig",
    "SpamResult",
    "check_keyword_spam",
    "check_repeated_links",
    "check_repeated_phrases",
    "check_caps_ratio",
    "check_punct_density",
    # Phase 2 — PII + pipeline
    "PIIFilter",
    "PIIFilterConfig",
    "PIIRedactionResult",
    "PIIMatch",
    "FilteringPipeline",
    "FilteringPipelineConfig",
    "FilteringMetrics",
    "ArticleFilterResult",
]
