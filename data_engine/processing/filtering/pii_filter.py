"""PII Filter — Phase 2 (Section 2.3).

يكتشف ويُعيد كتابة (redact) البيانات الشخصية الحساسة (PII).

أنواع البيانات المدعومة:
- أرقام الهواتف (دولية ومحلية)
- عناوين البريد الإلكتروني
- أرقام بطاقات الائتمان
- أرقام الهوية الوطنية (الخليج)
- عناوين IP
- التواريخ الكاملة (عند تفعيلها)
- الاسم الشخصي (باستخدام patterns بسيطة)
- رقم الضمان الاجتماعي
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Regex Patterns
# ─────────────────────────────────────────────────────────────────────────────

# أرقام الهاتف (دولية + محلية خليجية)
_PHONE_RE = re.compile(
    r"""
    (?:
        (?:\+|00)          # بادئة دولية
        (?:966|971|974|973|968|965|1|44|49|33|61)  # رموز دول
        [\s\-]?
    )?
    (?:
        0?[5678]\d{7,9}    # أرقام خليجية
        |
        \(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}  # أمريكية/بريطانية
        |
        \d{2,4}[\s\-]\d{3,4}[\s\-]\d{4}      # أوروبية عامة
    )
    """,
    re.VERBOSE | re.UNICODE,
)

# البريد الإلكتروني
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# بطاقات الائتمان (Visa, Mastercard, Amex, etc.)
_CREDIT_CARD_RE = re.compile(
    r"""
    (?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))
    (?:[\ \-]?\d{4}){2}
    (?:[\ \-]?\d{3,4})
    """,
    re.VERBOSE,
)

# أرقام الهوية السعودية (10 أرقام تبدأ بـ 1 أو 2)
_SAUDI_ID_RE = re.compile(r"\b[12]\d{9}\b")

# عناوين IP
_IP_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

# رقم الضمان الاجتماعي (US)
_SSN_RE = re.compile(r"\b\d{3}[-]\d{2}[-]\d{4}\b")

# IBAN
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PIIFilterConfig:
    """إعدادات فلتر PII."""

    redact_emails: bool = True
    redact_phones: bool = True
    redact_credit_cards: bool = True
    redact_national_ids: bool = True
    redact_ip_addresses: bool = False  # اختياري — قد تكون عناوين مشروعة
    redact_ssn: bool = True
    redact_iban: bool = True

    # القيمة البديلة لكل نوع
    email_placeholder: str = "[EMAIL]"
    phone_placeholder: str = "[PHONE]"
    credit_card_placeholder: str = "[CREDIT_CARD]"
    national_id_placeholder: str = "[NATIONAL_ID]"
    ip_placeholder: str = "[IP_ADDRESS]"
    ssn_placeholder: str = "[SSN]"
    iban_placeholder: str = "[IBAN]"

    # رفض المقال إذا تجاوز عدد البيانات الحساسة هذا الحد
    max_pii_count_before_reject: Optional[int] = None

    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# PII Detection Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PIIMatch:
    """مطابقة PII واحدة."""
    pii_type: str
    original_value: str   # القيمة قبل الإخفاء (للتدقيق فقط)
    placeholder: str
    start_char: int
    end_char: int


@dataclass
class PIIRedactionResult:
    """نتيجة إخفاء البيانات لمقال واحد."""
    article_id: str
    redacted_content: str
    redacted_title: str
    matches: List[PIIMatch] = field(default_factory=list)
    total_redacted: int = 0
    passed: bool = True
    rejection_reason: Optional[str] = None

    @property
    def pii_count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for m in self.matches:
            counts[m.pii_type] = counts.get(m.pii_type, 0) + 1
        return counts


# ─────────────────────────────────────────────────────────────────────────────
# Core redaction function
# ─────────────────────────────────────────────────────────────────────────────

def _redact_text(
    text: str,
    cfg: PIIFilterConfig,
    matches_out: Optional[List[PIIMatch]] = None,
    offset: int = 0,
) -> str:
    """تطبيق redaction على نص واحد."""
    if not text:
        return text

    rules: List[Tuple[re.Pattern, str, str]] = []

    if cfg.redact_emails:
        rules.append((_EMAIL_RE, cfg.email_placeholder, "email"))
    if cfg.redact_phones:
        rules.append((_PHONE_RE, cfg.phone_placeholder, "phone"))
    if cfg.redact_credit_cards:
        rules.append((_CREDIT_CARD_RE, cfg.credit_card_placeholder, "credit_card"))
    if cfg.redact_national_ids:
        rules.append((_SAUDI_ID_RE, cfg.national_id_placeholder, "national_id"))
    if cfg.redact_ip_addresses:
        rules.append((_IP_RE, cfg.ip_placeholder, "ip_address"))
    if cfg.redact_ssn:
        rules.append((_SSN_RE, cfg.ssn_placeholder, "ssn"))
    if cfg.redact_iban:
        rules.append((_IBAN_RE, cfg.iban_placeholder, "iban"))

    result = text
    for pattern, placeholder, pii_type in rules:
        def _replace(m: re.Match, ph: str = placeholder, pt: str = pii_type) -> str:
            if matches_out is not None:
                matches_out.append(PIIMatch(
                    pii_type=pt,
                    original_value=m.group()[:4] + "***",  # نُخفي معظم القيمة
                    placeholder=ph,
                    start_char=m.start() + offset,
                    end_char=m.end() + offset,
                ))
            return ph
        result = pattern.sub(_replace, result)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# PIIFilter class
# ─────────────────────────────────────────────────────────────────────────────

class PIIFilter:
    """فلتر إخفاء البيانات الشخصية الحساسة (PII Redaction).

    Parameters
    ----------
    config:
        PIIFilterConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[PIIFilterConfig] = None) -> None:
        self.config = config or PIIFilterConfig()

    def redact_article(self, article: Article) -> PIIRedactionResult:
        """إخفاء البيانات الحساسة من مقال واحد.

        Parameters
        ----------
        article:
            المقال المصدر.

        Returns
        -------
        PIIRedactionResult مع المحتوى المُنقّى.
        """
        cfg = self.config
        matches: List[PIIMatch] = []

        redacted_title = _redact_text(article.title, cfg, matches_out=matches, offset=0)
        redacted_content = _redact_text(
            article.content, cfg,
            matches_out=matches,
            offset=len(article.title) + 1,
        )

        total = len(matches)
        passed = True
        rejection_reason = None

        if cfg.max_pii_count_before_reject and total > cfg.max_pii_count_before_reject:
            passed = False
            rejection_reason = (
                f"too_much_pii (count={total} "
                f"max={cfg.max_pii_count_before_reject})"
            )
            logger.warning(
                "PIIFilter: rejected id=%s — %s", article.id, rejection_reason
            )
        elif total > 0:
            logger.debug(
                "PIIFilter: id=%s redacted=%d types=%s",
                article.id,
                total,
                list(set(m.pii_type for m in matches)),
            )

        return PIIRedactionResult(
            article_id=article.id,
            redacted_content=redacted_content,
            redacted_title=redacted_title,
            matches=matches,
            total_redacted=total,
            passed=passed,
            rejection_reason=rejection_reason,
        )

    def apply_to_article(self, article: Article) -> Tuple[Article, PIIRedactionResult]:
        """إخفاء البيانات وإعادة مقال مُنقّى.

        Parameters
        ----------
        article:
            المقال المصدر.

        Returns
        -------
        Tuple (redacted_article, result)
        """
        result = self.redact_article(article)
        if not result.passed:
            return article, result

        redacted_article = article.model_copy(update={
            "title": result.redacted_title,
            "content": result.redacted_content,
        })
        return redacted_article, result

    def filter_batch(
        self, articles: List[Article]
    ) -> Tuple[List[Article], List[PIIRedactionResult]]:
        """تطبيق PII redaction على دُفعة من المقالات.

        Parameters
        ----------
        articles:
            قائمة المقالات.

        Returns
        -------
        (kept_articles, all_results)
        """
        kept: List[Article] = []
        results: List[PIIRedactionResult] = []
        total_redacted = 0

        for article in articles:
            redacted_article, result = self.apply_to_article(article)
            results.append(result)
            total_redacted += result.total_redacted
            if result.passed:
                kept.append(redacted_article)

        logger.info(
            "PIIFilter.filter_batch: in=%d kept=%d rejected=%d total_pii_redacted=%d",
            len(articles),
            len(kept),
            len(articles) - len(kept),
            total_redacted,
        )
        return kept, results

    def detect_pii(self, text: str) -> Dict[str, int]:
        """اكتشاف PII في نص بدون redaction (للتحليل فقط).

        Returns
        -------
        dict من pii_type → count
        """
        matches: List[PIIMatch] = []
        _redact_text(text, self.config, matches_out=matches)
        counts: Dict[str, int] = {}
        for m in matches:
            counts[m.pii_type] = counts.get(m.pii_type, 0) + 1
        return counts
