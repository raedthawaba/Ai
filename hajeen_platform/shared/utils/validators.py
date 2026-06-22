import re
from urllib.parse import urlparse

def validate_url(url: str) -> bool:
    """Check if a string is a valid URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def validate_language_code(code: str) -> bool:
    """Simple check for ISO 639-1 language codes (2 letters)."""
    return bool(re.match(r'^[a-z]{2}$', code))

def validate_cron_expression(expression: str) -> bool:
    """Basic validation for cron expressions."""
    # This is a very basic regex for standard 5-field cron
    cron_regex = r'^(\*|([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])|\*\/([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])) (\*|([0-9]|1[0-9]|2[0-3])|\*\/([0-9]|1[0-9]|2[0-3])) (\*|([1-9]|1[0-9]|2[0-9]|3[0-1])|\*\/([1-9]|1[0-9]|2[0-9]|3[0-1])) (\*|([1-9]|1[0-2])|\*\/([1-9]|1[0-2])) (\*|([0-6])|\*\/([0-6]))$'
    return bool(re.match(cron_regex, expression))
