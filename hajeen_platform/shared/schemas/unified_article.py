"""Unified Article Schema — Phase 6.5.

Schema موحّد يُستخدم عبر جميع مصادر البيانات:
  - RSS Channels
  - Web Crawlers
  - API Connectors
  - Processing Pipeline
  - Storage Layer (raw → bronze → silver → gold)
  - Embedding Pipeline
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from shared.utils.datetime_utils import utc_now


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    """نوع مصدر المقال."""
    RSS = "rss"
    CRAWLER = "crawler"
    API = "api"
    MANUAL = "manual"
    DEMO = "demo"
    UNKNOWN = "unknown"


class ArticleProcessingStage(str, Enum):
    """مرحلة المعالجة الحالية للمقال."""
    RAW = "raw"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    EMBEDDED = "embedded"


class ContentLanguage(str, Enum):
    """اللغات المدعومة."""
    ARABIC = "ar"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────────

class EntityMention(BaseModel):
    """كيان مُستخرج من النص."""
    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    start_char: int = Field(default=0, ge=0)
    end_char: int = Field(default=0, ge=0)
    score: float = Field(default=1.0, ge=0.0, le=1.0)


class KeywordEntry(BaseModel):
    """كلمة مفتاحية مُستخرجة مع درجة الأهمية."""
    model_config = ConfigDict(extra="ignore")

    keyword: str = Field(..., min_length=1)
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    count: int = Field(default=1, ge=1)


class ArticleProcessingMetadata(BaseModel):
    """بيانات وصفية لمراحل المعالجة."""
    model_config = ConfigDict(extra="ignore")

    pipeline_run_id: Optional[str] = None
    processing_stage: ArticleProcessingStage = ArticleProcessingStage.RAW
    processing_duration_ms: float = 0.0
    processing_errors: List[str] = Field(default_factory=list)
    stage_timestamps: Dict[str, str] = Field(default_factory=dict)
    word_count: int = 0
    char_count: int = 0
    sentence_count: int = 0
    content_hash: Optional[str] = None
    url_hash: Optional[str] = None
    dedup_checked: bool = False
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Unified Article
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedArticle(BaseModel):
    """Schema موحّد للمقال — يُستخدم عبر جميع المصادر والطبقات.

    الحقول الأساسية:
    - id, source, source_type, url, title
    - raw_content, cleaned_content, summary
    - language, entities, keywords, categories
    - chunk_ids, embedding_id, metadata
    - created_at, updated_at
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )

    # ── هوية المقال ─────────────────────────────────────────────────────────
    id: str = Field(..., min_length=1, description="معرّف المقال الفريد")
    source: str = Field(..., min_length=1, description="معرّف مصدر القناة")
    source_type: SourceType = Field(
        default=SourceType.UNKNOWN, description="نوع المصدر"
    )
    url: str = Field(..., description="رابط المقال الأصلي")

    # ── المحتوى ─────────────────────────────────────────────────────────────
    title: str = Field(..., min_length=1, description="عنوان المقال")
    raw_content: str = Field(
        default="", description="المحتوى الخام قبل المعالجة"
    )
    cleaned_content: str = Field(
        default="", description="المحتوى بعد تنظيف HTML والتطبيع"
    )
    summary: Optional[str] = Field(
        default=None, description="ملخص تلقائي للمقال"
    )

    # ── اللغة والتصنيف ──────────────────────────────────────────────────────
    language: str = Field(default="en", description="رمز اللغة ISO 639-1")
    entities: List[EntityMention] = Field(
        default_factory=list, description="الكيانات المُستخرجة"
    )
    keywords: List[KeywordEntry] = Field(
        default_factory=list, description="الكلمات المفتاحية مع درجاتها"
    )
    categories: List[str] = Field(
        default_factory=list, description="تصنيفات المقال"
    )
    tags: List[str] = Field(
        default_factory=list, description="الوسوم"
    )
    author: Optional[str] = Field(default=None, description="المؤلف")

    # ── تكامل Chunking & Embeddings ─────────────────────────────────────────
    chunk_ids: List[str] = Field(
        default_factory=list, description="معرّفات الـ chunks المرتبطة"
    )
    embedding_id: Optional[str] = Field(
        default=None, description="معرّف الـ embedding للمقال كاملاً"
    )
    chunk_count: int = Field(
        default=0, description="عدد الـ chunks الفعلي"
    )

    # ── التواريخ ─────────────────────────────────────────────────────────────
    published_at: Optional[datetime] = Field(
        default=None, description="تاريخ النشر الأصلي"
    )
    extracted_at: datetime = Field(
        default_factory=utc_now, description="وقت الاستخراج"
    )
    created_at: datetime = Field(
        default_factory=utc_now, description="وقت الإنشاء في النظام"
    )
    updated_at: datetime = Field(
        default_factory=utc_now, description="آخر تحديث"
    )

    # ── بيانات التخزين ──────────────────────────────────────────────────────
    raw_storage_key: Optional[str] = Field(
        default=None, description="مفتاح التخزين في الـ raw layer"
    )
    bronze_storage_key: Optional[str] = Field(
        default=None, description="مفتاح التخزين في الـ bronze layer"
    )
    silver_storage_key: Optional[str] = Field(
        default=None, description="مفتاح التخزين في الـ silver layer"
    )
    gold_storage_key: Optional[str] = Field(
        default=None, description="مفتاح التخزين في الـ gold layer"
    )

    # ── البيانات الوصفية ────────────────────────────────────────────────────
    processing: ArticleProcessingMetadata = Field(
        default_factory=ArticleProcessingMetadata,
        description="بيانات وصفية لمراحل المعالجة"
    )
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="بيانات وصفية إضافية"
    )

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("id", "source", "title")
    @classmethod
    def strip_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("لا يمكن أن يكون الحقل فارغاً.")
        return v

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        return v.strip().lower()[:2] if v else "en"

    # ── Methods ──────────────────────────────────────────────────────────────

    def content_for_processing(self) -> str:
        """إرجاع أفضل محتوى متاح للمعالجة."""
        return self.cleaned_content or self.raw_content or self.title

    def compute_content_hash(self) -> str:
        """حساب هاش SHA-256 للمحتوى الموحّد."""
        text = _normalize_for_hash(self.title) + "\n" + _normalize_for_hash(
            (self.cleaned_content or self.raw_content)[:500]
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def compute_url_hash(self) -> str:
        """حساب هاش SHA-256 للرابط."""
        url = self.url.strip().lower().rstrip("/")
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def mark_as_chunked(self, chunk_ids: List[str]) -> None:
        """تحديث معرّفات الـ chunks."""
        self.chunk_ids = chunk_ids
        self.chunk_count = len(chunk_ids)
        self.updated_at = utc_now()

    def mark_as_embedded(self, embedding_id: str) -> None:
        """تحديث معرّف الـ embedding."""
        self.embedding_id = embedding_id
        self.processing.processing_stage = ArticleProcessingStage.EMBEDDED
        self.updated_at = utc_now()

    def advance_stage(self, stage: ArticleProcessingStage) -> None:
        """تقدّم المقال لمرحلة معالجة جديدة."""
        self.processing.processing_stage = stage
        self.processing.stage_timestamps[stage.value] = utc_now().isoformat()
        self.updated_at = utc_now()

    @classmethod
    def from_legacy_article(cls, article: Any) -> "UnifiedArticle":
        """تحويل Article القديم إلى UnifiedArticle.

        يُستخدم للتوافق مع القنوات الموجودة.
        """
        from shared.schemas.article import Article
        if not isinstance(article, Article):
            raise TypeError(f"المدخل يجب أن يكون Article، وليس {type(article)}")

        meta = article.metadata
        keywords = [
            KeywordEntry(keyword=tag, score=1.0) for tag in meta.tags
        ]
        entities = [
            EntityMention(
                text=e.text,
                label=e.label,
                start_char=e.start_char,
                end_char=e.end_char,
                score=e.score,
            )
            for e in meta.entities
        ]

        return cls(
            id=article.id,
            source=meta.source_id,
            source_type=SourceType.RSS,
            url=str(article.url),
            title=article.title,
            raw_content=article.content,
            cleaned_content=article.content,
            summary=article.summary,
            language=meta.language,
            entities=entities,
            keywords=keywords,
            tags=list(meta.tags),
            author=meta.author,
            published_at=article.published_at,
            extracted_at=article.extracted_at,
            created_at=utc_now(),
            updated_at=utc_now(),
            extra_metadata=dict(meta.extra),
        )

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dict قابل للتسلسل."""
        return self.model_dump(mode="json")

    @property
    def keyword_list(self) -> List[str]:
        """قائمة نصية بالكلمات المفتاحية."""
        return [k.keyword for k in self.keywords]

    @property
    def entity_texts(self) -> List[str]:
        """قائمة نصية بالكيانات."""
        return [e.text for e in self.entities]

    @property
    def word_count(self) -> int:
        """عدد الكلمات في المحتوى."""
        return len(self.content_for_processing().split())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_for_hash(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def articles_to_unified(articles: List[Any]) -> List[UnifiedArticle]:
    """تحويل قائمة Articles القديمة إلى UnifiedArticles."""
    result = []
    for art in articles:
        try:
            result.append(UnifiedArticle.from_legacy_article(art))
        except Exception:
            pass
    return result
