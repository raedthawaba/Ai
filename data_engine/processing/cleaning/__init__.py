"""Text cleaning module."""

from .text_cleaner import (
    TextCleaner,
    CleanerConfig,
    clean_text,
    strip_html,
    decode_html_entities,
    remove_urls,
    remove_emails,
    remove_harakat,
    remove_tatweel,
    normalize_alef,
    normalize_ta_marbuta,
    normalize_unicode,
    fix_whitespace,
)

# Phase 5 — HTML cleaning & text normalisation
from .html_cleaner import (
    HTMLCleaner,
    clean_html,
    remove_html,
    remove_scripts,
    remove_ads,
    extract_main_content,
    normalize_whitespace,
)

from .text_normalizer import (
    TextNormalizer,
    NormalizerConfig,
    normalize_text,
    normalize_unicode as normalize_unicode_nfc,
    remove_emojis,
    remove_zero_width_chars,
    reduce_repeated_punctuation,
    normalize_arabic_extended,
    fix_whitespace as fix_whitespace_normalizer,
)

# Phase 2 — unified cleaning pipeline
from .cleaning_pipeline import (
    CleaningPipeline,
    CleaningPipelineConfig,
    CleaningMetrics,
    BatchCleaningMetrics,
)

__all__ = [
    # Phase 4
    "TextCleaner",
    "CleanerConfig",
    "clean_text",
    "strip_html",
    "decode_html_entities",
    "remove_urls",
    "remove_emails",
    "remove_harakat",
    "remove_tatweel",
    "normalize_alef",
    "normalize_ta_marbuta",
    "normalize_unicode",
    "fix_whitespace",
    # Phase 5 — html_cleaner
    "HTMLCleaner",
    "clean_html",
    "remove_html",
    "remove_scripts",
    "remove_ads",
    "extract_main_content",
    "normalize_whitespace",
    # Phase 5 — text_normalizer
    "TextNormalizer",
    "NormalizerConfig",
    "normalize_text",
    "normalize_unicode_nfc",
    "remove_emojis",
    "remove_zero_width_chars",
    "reduce_repeated_punctuation",
    "normalize_arabic_extended",
    "fix_whitespace_normalizer",
    # Phase 2 — cleaning pipeline
    "CleaningPipeline",
    "CleaningPipelineConfig",
    "CleaningMetrics",
    "BatchCleaningMetrics",
]
