import re

def normalize_text(text: str) -> str:
    """Basic text normalization."""
    if not text:
        return ""
    # Remove extra whitespace and normalize case (optional, but keeping it simple for now)
    return text.strip()

def clean_whitespace(text: str) -> str:
    """Replace multiple whitespaces with a single space."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to a maximum length."""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(' ', 1)[0] + suffix
