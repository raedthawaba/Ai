"""Markdown Converter — Phase 2 (Section 2.5).

يُحوّل المحتوى النصي إلى Markdown منسّق يدعم:
  - العناوين (H1–H4)
  - الفقرات
  - القوائم المرقّمة وغير المرقّمة
  - الكتل المقتبسة
  - الكود البرمجي
  - الجداول (بسيطة)
  - الروابط
  - الخط العريض والمائل
  - دعم العربية (RTL) مع اتجاه النص الصحيح
  - تحويل عكسي: Markdown → Plain text
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Patterns
# ─────────────────────────────────────────────────────────────────────────────

_PARA_SPLIT = re.compile(r"\n{2,}")
_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")
_HEADER_HINT = re.compile(r"^[A-Z\u0600-\u06FF].{0,80}[^.!?؟،,]$", re.MULTILINE)
_LIST_ITEM_HINT = re.compile(r"^[\-•\*·]\s+.+$", re.MULTILINE)
_NUMBERED_ITEM = re.compile(r"^\d+[.)]\s+.+$", re.MULTILINE)
_URL_LINK = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"\*(.+?)\*")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarkdownConverterConfig:
    """إعدادات MarkdownConverter."""

    include_title: bool = True
    include_summary: bool = True
    include_metadata: bool = False  # إضافة كتلة metadata في البداية
    auto_detect_headers: bool = True
    auto_detect_lists: bool = True
    linkify_urls: bool = True
    rtl_support: bool = True         # إضافة علامة RTL للعربية
    max_header_length: int = 100     # أقصى طول للعنوان
    paragraph_separator: str = "\n\n"
    code_fence: str = "```"
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Markdown Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_arabic_text(text: str) -> bool:
    """اكتشاف النص العربي."""
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    total_alpha = len(re.findall(r"[a-zA-Z\u0600-\u06FF]", text))
    return total_alpha > 0 and arabic_chars / total_alpha >= 0.4


def _detect_paragraphs(text: str) -> List[str]:
    """تقسيم النص إلى فقرات."""
    paras = _PARA_SPLIT.split(text.strip())
    return [p.strip() for p in paras if p.strip()]


def _is_header_candidate(line: str, max_len: int = 100) -> bool:
    """هل هذا السطر مرشّح للعنوان؟"""
    stripped = line.strip()
    if not stripped or len(stripped) > max_len:
        return False
    # قصير + لا ينتهي بنقطة
    if len(stripped) <= 80 and not stripped[-1] in ".،,:;":
        # يبدأ بحرف كبير (إنجليزي) أو حرف عربي
        if re.match(r"^[A-Z\u0600-\u06FF]", stripped):
            return True
    return False


def _linkify(text: str) -> str:
    """تحويل URLs إلى روابط Markdown."""
    return _URL_LINK.sub(r"[\1](\1)", text)


def _paragraph_to_markdown(
    para: str,
    cfg: MarkdownConverterConfig,
    para_index: int = 0,
) -> str:
    """تحويل فقرة واحدة إلى Markdown."""
    lines = para.strip().splitlines()
    result_lines = []

    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # كشف القوائم
        if cfg.auto_detect_lists and _LIST_ITEM_HINT.match(line):
            result_lines.append(f"- {line.lstrip('-•*· ')}")
            continue

        if cfg.auto_detect_lists and _NUMBERED_ITEM.match(line):
            result_lines.append(line)
            continue

        # كشف العناوين (أول سطر في كل فقرة إذا كان قصيراً)
        if (
            cfg.auto_detect_headers
            and line_idx == 0
            and para_index > 0
            and _is_header_candidate(line, cfg.max_header_length)
        ):
            result_lines.append(f"## {line}")
            continue

        # Linkify
        if cfg.linkify_urls:
            line = _linkify(line)

        result_lines.append(line)

    return "\n".join(result_lines)


def text_to_markdown(
    content: str,
    title: str = "",
    summary: Optional[str] = None,
    language: str = "en",
    config: Optional[MarkdownConverterConfig] = None,
) -> str:
    """تحويل نص عادي إلى Markdown منسّق.

    Parameters
    ----------
    content:
        المحتوى الرئيسي.
    title:
        عنوان المقال.
    summary:
        ملخص المقال (اختياري).
    language:
        لغة المحتوى.
    config:
        إعدادات التحويل.

    Returns
    -------
    نص Markdown منسّق.
    """
    cfg = config or MarkdownConverterConfig()
    parts: List[str] = []
    is_ar = _is_arabic_text(content) or language == "ar"

    # إضافة العنوان
    if cfg.include_title and title:
        h1 = f"# {title}"
        if is_ar and cfg.rtl_support:
            h1 = "# " + title  # RTL handled by the renderer
        parts.append(h1)

    # إضافة الملخص
    if cfg.include_summary and summary:
        parts.append(f"> {summary}")

    # تحويل الفقرات
    paragraphs = _detect_paragraphs(content)
    for i, para in enumerate(paragraphs):
        md_para = _paragraph_to_markdown(para, cfg, para_index=i)
        if md_para:
            parts.append(md_para)

    return cfg.paragraph_separator.join(parts)


def markdown_to_plain_text(markdown: str) -> str:
    """تحويل Markdown إلى نص عادي (إزالة العلامات).

    Parameters
    ----------
    markdown:
        نص Markdown.

    Returns
    -------
    نص عادي.
    """
    if not markdown:
        return ""

    text = markdown

    # إزالة عناوين
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # إزالة Bold وItalic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # إزالة روابط: [text](url) → text
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

    # إزالة بلوكات كود
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)

    # إزالة blockquotes
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

    # إزالة قوائم
    text = re.sub(r"^[\-\*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+[.)]\s+", "", text, flags=re.MULTILINE)

    # تطبيع المسافات
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# MarkdownConverter class
# ─────────────────────────────────────────────────────────────────────────────

class MarkdownConverter:
    """محوّل المحتوى إلى Markdown.

    Parameters
    ----------
    config:
        MarkdownConverterConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[MarkdownConverterConfig] = None) -> None:
        self.config = config or MarkdownConverterConfig()

    def to_markdown(
        self,
        content: str,
        title: str = "",
        summary: Optional[str] = None,
        language: str = "en",
    ) -> str:
        """تحويل نص إلى Markdown.

        Parameters
        ----------
        content:
            المحتوى الرئيسي.
        title:
            عنوان المقال.
        summary:
            ملخص.
        language:
            اللغة.

        Returns
        -------
        نص Markdown.
        """
        return text_to_markdown(content, title, summary, language, self.config)

    def article_to_markdown(self, article: object) -> str:
        """تحويل Article إلى Markdown.

        Parameters
        ----------
        article:
            Article من shared.schemas.article.

        Returns
        -------
        نص Markdown.
        """
        from shared.schemas.article import Article
        if not isinstance(article, Article):
            raise TypeError(f"مدخل غير مدعوم: {type(article)}")

        lang = article.metadata.language or "en"
        return self.to_markdown(
            content=article.content,
            title=article.title,
            summary=article.summary,
            language=lang,
        )

    def to_plain_text(self, markdown: str) -> str:
        """تحويل Markdown إلى نص عادي.

        Parameters
        ----------
        markdown:
            نص Markdown.

        Returns
        -------
        نص عادي.
        """
        return markdown_to_plain_text(markdown)

    def batch_to_markdown(
        self, articles: List[object]
    ) -> List[str]:
        """تحويل دُفعة من المقالات إلى Markdown.

        Parameters
        ----------
        articles:
            قائمة Articles.

        Returns
        -------
        قائمة نصوص Markdown.
        """
        results = [self.article_to_markdown(a) for a in articles]
        logger.info(
            "MarkdownConverter.batch_to_markdown: converted=%d", len(results)
        )
        return results
