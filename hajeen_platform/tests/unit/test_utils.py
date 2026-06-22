import pytest
from datetime import datetime
from shared.utils import (
    normalize_text, clean_whitespace, truncate_text,
    validate_url, validate_language_code, validate_cron_expression,
    utc_now, generate_channel_id, generate_article_id
)
from shared.exceptions import ValidationException

def test_text_utils():
    assert normalize_text("  hello  ") == "hello"
    assert clean_whitespace("hello    world") == "hello world"
    assert truncate_text("this is a long sentence", 10) == "this is a..."

def test_validators():
    assert validate_url("https://google.com") is True
    assert validate_url("invalid") is False
    assert validate_language_code("ar") is True
    assert validate_language_code("arabic") is False
    assert validate_cron_expression("* * * * *") is True
    assert validate_cron_expression("99 99 99 99 99") is False

def test_datetime_utils():
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None

def test_id_generators():
    cid = generate_channel_id()
    assert cid.startswith("ch_")
    assert len(cid) > 5
    
    url = "https://example.com/news1"
    aid1 = generate_article_id(url)
    aid2 = generate_article_id(url)
    assert aid1 == aid2
    assert aid1.startswith("art_")

def test_exceptions():
    with pytest.raises(ValidationException) as exc:
        raise ValidationException("Invalid data", details={"field": "email"})
    assert exc.value.message == "Invalid data"
    assert exc.value.details["field"] == "email"
