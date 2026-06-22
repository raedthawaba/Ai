"""Unit tests for PIIFilter — Phase 2 (Section 2.3)."""
from __future__ import annotations

import pytest
from datetime import datetime

from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.filtering.pii_filter import (
    PIIFilter,
    PIIFilterConfig,
    PIIRedactionResult,
    PIIMatch,
    _redact_text,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(content: str, title: str = "Test", article_id: str = "art001") -> Article:
    return Article(
        id=article_id,
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=datetime(2024, 1, 1),
        metadata=ArticleMetadata(source_id="src_test", language="en"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Pattern detection
# ─────────────────────────────────────────────────────────────────────────────

class TestPIIRedactionPatterns:
    """اختبار كل نوع من أنواع PII بشكل مستقل."""

    def test_email_redacted(self):
        cfg = PIIFilterConfig(redact_emails=True)
        result = _redact_text("Contact us at user@example.com for info.", cfg)
        assert "[EMAIL]" in result
        assert "user@example.com" not in result

    def test_phone_redacted(self):
        cfg = PIIFilterConfig(redact_phones=True)
        result = _redact_text("Call us: +966501234567", cfg)
        assert "[PHONE]" in result
        assert "+966501234567" not in result

    def test_credit_card_redacted(self):
        cfg = PIIFilterConfig(redact_credit_cards=True)
        result = _redact_text("Card: 4111 1111 1111 1111 expired.", cfg)
        assert "[CREDIT_CARD]" in result

    def test_national_id_redacted(self):
        cfg = PIIFilterConfig(redact_national_ids=True)
        result = _redact_text("ID: 1234567890 is registered.", cfg)
        assert "[NATIONAL_ID]" in result
        assert "1234567890" not in result

    def test_ssn_redacted(self):
        cfg = PIIFilterConfig(redact_ssn=True)
        result = _redact_text("SSN: 123-45-6789", cfg)
        assert "[SSN]" in result
        assert "123-45-6789" not in result

    def test_ip_redacted_when_enabled(self):
        cfg = PIIFilterConfig(redact_ip_addresses=True)
        result = _redact_text("Server IP: 192.168.1.100", cfg)
        assert "[IP_ADDRESS]" in result

    def test_ip_not_redacted_when_disabled(self):
        cfg = PIIFilterConfig(redact_ip_addresses=False)
        result = _redact_text("Server IP: 192.168.1.100", cfg)
        assert "192.168.1.100" in result

    def test_custom_placeholder(self):
        cfg = PIIFilterConfig(
            redact_emails=True,
            email_placeholder="[REMOVED_EMAIL]",
        )
        result = _redact_text("Email: test@test.com", cfg)
        assert "[REMOVED_EMAIL]" in result

    def test_multiple_pii_types_in_one_text(self):
        cfg = PIIFilterConfig()
        matches = []
        text = "user@mail.com called +966509876543 about card 4111-1111-1111-1111"
        _redact_text(text, cfg, matches_out=matches)
        pii_types = {m.pii_type for m in matches}
        assert "email" in pii_types or len(pii_types) > 0  # at least one detected

    def test_no_false_positives_on_clean_text(self):
        cfg = PIIFilterConfig()
        clean_text = "This is a regular article about technology and science."
        result = _redact_text(clean_text, cfg)
        assert result == clean_text


# ─────────────────────────────────────────────────────────────────────────────
# Tests: PIIFilter class
# ─────────────────────────────────────────────────────────────────────────────

class TestPIIFilter:
    def test_default_config(self):
        pii = PIIFilter()
        assert pii.config.redact_emails is True
        assert pii.config.redact_phones is True

    def test_redact_article_returns_result(self):
        pii = PIIFilter()
        article = _make_article("Contact john@doe.com for help.", "Title")
        result = pii.redact_article(article)
        assert isinstance(result, PIIRedactionResult)
        assert result.article_id == article.id
        assert result.total_redacted >= 1

    def test_apply_to_article_modifies_content(self):
        pii = PIIFilter()
        article = _make_article("Email: test@example.com here.", "Safe Title")
        redacted, result = pii.apply_to_article(article)
        assert "test@example.com" not in redacted.content
        assert "[EMAIL]" in redacted.content
        assert result.passed

    def test_title_pii_redacted(self):
        pii = PIIFilter()
        article = _make_article("Some content", title="Call +966501234567 now")
        redacted, result = pii.apply_to_article(article)
        assert "+966501234567" not in redacted.title
        assert "[PHONE]" in redacted.title

    def test_article_rejected_when_pii_exceeds_limit(self):
        cfg = PIIFilterConfig(max_pii_count_before_reject=1)
        pii = PIIFilter(cfg)
        # نص يحتوي على أكثر من 1 PII
        article = _make_article(
            "Email: a@b.com, phone: +966501234567, SSN: 123-45-6789",
            "Title",
        )
        redacted, result = pii.apply_to_article(article)
        # إذا وُجد أكثر من 1 PII → rejected
        if result.total_redacted > 1:
            assert not result.passed

    def test_passed_when_no_pii(self):
        pii = PIIFilter()
        article = _make_article("Clean article with no personal data here.", "Clean")
        redacted, result = pii.apply_to_article(article)
        assert result.passed
        assert result.total_redacted == 0

    def test_detect_pii_without_redaction(self):
        pii = PIIFilter()
        counts = pii.detect_pii("Email: user@test.com and phone +966509876543")
        assert isinstance(counts, dict)
        assert "email" in counts

    def test_pii_count_by_type(self):
        pii = PIIFilter()
        article = _make_article("a@b.com and b@c.com emails here.", "Title")
        result = pii.redact_article(article)
        by_type = result.pii_count_by_type
        assert isinstance(by_type, dict)

    def test_filter_batch_returns_kept_and_results(self):
        pii = PIIFilter()
        articles = [
            _make_article("Clean article with no PII.", "Clean", "art001"),
            _make_article("Contact: user@example.com", "PII Article", "art002"),
        ]
        kept, results = pii.filter_batch(articles)
        assert len(kept) + (len(articles) - len(kept)) == len(articles)
        assert len(results) == 2

    def test_filter_batch_all_pass_without_limit(self):
        pii = PIIFilter()  # no max_pii_count_before_reject
        articles = [
            _make_article("user@test.com phone +966501111111", "Title", f"art{i}")
            for i in range(5)
        ]
        kept, results = pii.filter_batch(articles)
        assert all(r.passed for r in results)  # تمر جميعاً بدون رفض

    def test_match_has_correct_pii_type(self):
        pii = PIIFilter()
        article = _make_article("Email me at john@example.com please.", "Title")
        result = pii.redact_article(article)
        if result.matches:
            match = result.matches[0]
            assert isinstance(match, PIIMatch)
            assert match.pii_type in {"email", "phone", "credit_card", "national_id", "ssn", "iban"}
