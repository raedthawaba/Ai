"""Deduplication Engine — Phase 6.5.

نظام إزالة التكرار الشامل يعمل على 3 مستويات:
  1. Article Deduplication  — منع تكرار المقالات
  2. Chunk Deduplication    — منع تكرار الـ chunks
  3. Embedding Deduplication — منع تكرار الـ embeddings

يدعم:
  - content hashing (SHA-256)
  - normalized hashing (تطبيع قبل الهاش)
  - URL-based deduplication
  - similarity detection (difflib)
  - SQLite-backed persistence للهاشات عبر الجلسات
"""
from __future__ import annotations

import difflib
import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger(__name__)

_DB_PATH = Path("storage_data/metadata/dedup_state.db")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """تطبيع النص قبل الهاش: lowercase + مسافات."""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    # إزالة علامات الترقيم الغير ضرورية
    text = re.sub(r"[^\w\s\u0600-\u06FF]", "", text)
    return text


def compute_content_hash(title: str, content: str, preview: int = 500) -> str:
    """SHA-256 للعنوان + أول 500 حرف من المحتوى (موحّدَيْن)."""
    key = _normalize_text(title) + "\n" + _normalize_text(content[:preview])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def compute_url_hash(url: str) -> str:
    """SHA-256 للـ URL بعد التطبيع."""
    url = url.strip().lower().rstrip("/")
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def compute_normalized_hash(text: str) -> str:
    """SHA-256 للنص كاملاً بعد التطبيع الكامل."""
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def compute_similarity(text_a: str, text_b: str, preview: int = 500) -> float:
    """حساب التشابه النصي باستخدام difflib SequenceMatcher."""
    a = _normalize_text(text_a[:preview])
    b = _normalize_text(text_b[:preview])
    return difflib.SequenceMatcher(None, a, b).ratio()


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DeduplicationConfig:
    """إعدادات نظام إزالة التكرار."""

    # Article level
    deduplicate_urls: bool = True
    deduplicate_content: bool = True
    deduplicate_similar: bool = True
    similarity_threshold: float = 0.85
    content_preview_length: int = 500
    min_content_length: int = 30

    # Chunk level
    deduplicate_chunks: bool = True
    chunk_similarity_threshold: float = 0.90

    # Embedding level
    deduplicate_embeddings: bool = True

    # Persistence — حفظ الهاشات في SQLite عبر الجلسات
    persistent: bool = True
    db_path: Path = field(default_factory=lambda: _DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArticleDedupResult:
    """نتيجة إزالة التكرار من دُفعة مقالات."""
    unique_articles: List[Any] = field(default_factory=list)
    duplicate_ids: List[str] = field(default_factory=list)
    similarity_pairs: List[Tuple[str, str, float]] = field(default_factory=list)
    rejection_reasons: Dict[str, str] = field(default_factory=dict)

    @property
    def unique_count(self) -> int:
        return len(self.unique_articles)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_ids)

    def summary(self) -> Dict[str, Any]:
        return {
            "unique": self.unique_count,
            "duplicates": self.duplicate_count,
            "similarity_pairs": len(self.similarity_pairs),
        }


@dataclass
class ChunkDedupResult:
    """نتيجة إزالة التكرار من دُفعة chunks."""
    unique_chunks: List[Any] = field(default_factory=list)
    duplicate_ids: List[str] = field(default_factory=list)

    @property
    def unique_count(self) -> int:
        return len(self.unique_chunks)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_ids)


@dataclass
class EmbeddingDedupResult:
    """نتيجة إزالة التكرار من embedding IDs."""
    unique_ids: List[str] = field(default_factory=list)
    duplicate_ids: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Persistent State — SQLite
# ─────────────────────────────────────────────────────────────────────────────

class _PersistentHashStore:
    """تخزين الهاشات في SQLite للاستمرارية عبر الجلسات."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS article_hashes (
                hash TEXT PRIMARY KEY,
                hash_type TEXT NOT NULL,
                article_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS chunk_hashes (
                hash TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS embedding_hashes (
                hash TEXT PRIMARY KEY,
                embedding_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_art_type ON article_hashes(hash_type);
        """)
        self._db.commit()

    def has_article_hash(self, h: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM article_hashes WHERE hash=?", (h,)
        ).fetchone()
        return row is not None

    def add_article_hash(self, h: str, hash_type: str, article_id: str) -> None:
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO article_hashes (hash, hash_type, article_id) VALUES (?,?,?)",
                (h, hash_type, article_id),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("DedupStore: خطأ في حفظ هاش المقال — %s", exc)

    def has_chunk_hash(self, h: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM chunk_hashes WHERE hash=?", (h,)
        ).fetchone()
        return row is not None

    def add_chunk_hash(self, h: str, chunk_id: str, article_id: str) -> None:
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO chunk_hashes (hash, chunk_id, article_id) VALUES (?,?,?)",
                (h, chunk_id, article_id),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("DedupStore: خطأ في حفظ هاش الـ chunk — %s", exc)

    def has_embedding_hash(self, h: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM embedding_hashes WHERE hash=?", (h,)
        ).fetchone()
        return row is not None

    def add_embedding_hash(self, h: str, embedding_id: str, source_id: str) -> None:
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO embedding_hashes (hash, embedding_id, source_id) VALUES (?,?,?)",
                (h, embedding_id, source_id),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("DedupStore: خطأ في حفظ هاش الـ embedding — %s", exc)

    def article_count(self) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM article_hashes"
        ).fetchone()[0]

    def chunk_count(self) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM chunk_hashes"
        ).fetchone()[0]

    def reset_articles(self) -> None:
        self._db.execute("DELETE FROM article_hashes")
        self._db.commit()

    def reset_all(self) -> None:
        self._db.executescript(
            "DELETE FROM article_hashes; DELETE FROM chunk_hashes; DELETE FROM embedding_hashes;"
        )
        self._db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# DeduplicationEngine — الواجهة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────

class DeduplicationEngine:
    """نظام إزالة التكرار الشامل — Article + Chunk + Embedding.

    يحتفظ بالحالة في الذاكرة (في-الجلسة) وفي SQLite (عبر الجلسات).
    """

    def __init__(self, config: Optional[DeduplicationConfig] = None) -> None:
        self.config = config or DeduplicationConfig()

        # In-memory sets للسرعة
        self._url_hashes: Set[str] = set()
        self._content_hashes: Set[str] = set()
        self._chunk_hashes: Set[str] = set()
        self._embedding_hashes: Set[str] = set()

        # SQLite persistence
        self._store: Optional[_PersistentHashStore] = None
        if self.config.persistent:
            try:
                self._store = _PersistentHashStore(self.config.db_path)
                logger.debug("DeduplicationEngine: SQLite persistence نشط")
            except Exception as exc:
                logger.warning("DeduplicationEngine: فشل SQLite — %s", exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Article Deduplication
    # ─────────────────────────────────────────────────────────────────────────

    def deduplicate_articles(
        self,
        articles: List[Any],
        reset_session: bool = False,
    ) -> ArticleDedupResult:
        """إزالة تكرار المقالات.

        يقبل Article القديم أو UnifiedArticle الجديد.
        """
        if reset_session:
            self._url_hashes.clear()
            self._content_hashes.clear()

        cfg = self.config
        unique: List[Any] = []
        dup_ids: List[str] = []
        reasons: Dict[str, str] = {}

        for article in articles:
            article_id, title, content, url = self._extract_article_fields(article)

            if not content or len(content.strip()) < cfg.min_content_length:
                unique.append(article)
                continue

            reason = self._check_article_duplicate(
                article_id, title, content, url, update_state=True
            )
            if reason:
                dup_ids.append(article_id)
                reasons[article_id] = reason
                logger.debug("Dedup: تكرار id=%s سبب=%s", article_id, reason)
            else:
                unique.append(article)

        result = ArticleDedupResult(
            unique_articles=unique,
            duplicate_ids=dup_ids,
            rejection_reasons=reasons,
        )

        # Similarity detection
        if cfg.deduplicate_similar and len(unique) > 1:
            result = self._similarity_dedup(result)

        logger.info(
            "DeduplicationEngine: in=%d unique=%d dups=%d",
            len(articles), result.unique_count, result.duplicate_count,
        )
        return result

    def is_article_duplicate(self, article: Any) -> Tuple[bool, str]:
        """فحص إذا كان المقال مكرّراً (دون تحديث الحالة).

        Returns (is_dup, reason)
        """
        article_id, title, content, url = self._extract_article_fields(article)
        reason = self._check_article_duplicate(
            article_id, title, content, url, update_state=False
        )
        return (bool(reason), reason or "")

    # ─────────────────────────────────────────────────────────────────────────
    # Chunk Deduplication
    # ─────────────────────────────────────────────────────────────────────────

    def deduplicate_chunks(
        self,
        chunks: List[Any],
        reset_session: bool = False,
    ) -> ChunkDedupResult:
        """إزالة تكرار الـ chunks.

        يقبل DocumentChunk أو dict مع حقول chunk_id وtext.
        """
        if reset_session:
            self._chunk_hashes.clear()

        unique: List[Any] = []
        dup_ids: List[str] = []

        for chunk in chunks:
            chunk_id, text, article_id = self._extract_chunk_fields(chunk)
            h = compute_normalized_hash(text)

            is_dup = h in self._chunk_hashes
            if not is_dup and self._store:
                is_dup = self._store.has_chunk_hash(h)

            if is_dup:
                dup_ids.append(chunk_id)
                logger.debug("ChunkDedup: تكرار chunk_id=%s", chunk_id)
            else:
                self._chunk_hashes.add(h)
                if self._store:
                    self._store.add_chunk_hash(h, chunk_id, article_id)
                unique.append(chunk)

        if dup_ids:
            logger.info(
                "ChunkDedup: %d فريدة، %d مكرّرة", len(unique), len(dup_ids)
            )
        return ChunkDedupResult(unique_chunks=unique, duplicate_ids=dup_ids)

    # ─────────────────────────────────────────────────────────────────────────
    # Embedding Deduplication
    # ─────────────────────────────────────────────────────────────────────────

    def deduplicate_embeddings(
        self,
        embedding_requests: List[Dict[str, str]],
    ) -> EmbeddingDedupResult:
        """إزالة تكرار طلبات الـ embedding.

        كل طلب: {"source_id": ..., "text": ..., "embedding_id": ...}
        """
        unique_ids: List[str] = []
        dup_ids: List[str] = []

        for req in embedding_requests:
            embedding_id = req.get("embedding_id", "")
            text = req.get("text", "")
            source_id = req.get("source_id", "")

            h = compute_normalized_hash(text) if text else embedding_id
            is_dup = h in self._embedding_hashes
            if not is_dup and self._store:
                is_dup = self._store.has_embedding_hash(h)

            if is_dup:
                dup_ids.append(embedding_id)
            else:
                self._embedding_hashes.add(h)
                if self._store:
                    self._store.add_embedding_hash(h, embedding_id, source_id)
                unique_ids.append(embedding_id)

        return EmbeddingDedupResult(unique_ids=unique_ids, duplicate_ids=dup_ids)

    # ─────────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """إحصائيات الحالة الحالية."""
        result = {
            "memory": {
                "url_hashes": len(self._url_hashes),
                "content_hashes": len(self._content_hashes),
                "chunk_hashes": len(self._chunk_hashes),
                "embedding_hashes": len(self._embedding_hashes),
            }
        }
        if self._store:
            result["persistent"] = {
                "articles": self._store.article_count(),
                "chunks": self._store.chunk_count(),
            }
        return result

    def reset(self) -> None:
        """إعادة تعيين الحالة في الذاكرة."""
        self._url_hashes.clear()
        self._content_hashes.clear()
        self._chunk_hashes.clear()
        self._embedding_hashes.clear()

    def reset_persistent(self) -> None:
        """إعادة تعيين SQLite أيضاً."""
        self.reset()
        if self._store:
            self._store.reset_all()

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_article_fields(
        self, article: Any
    ) -> Tuple[str, str, str, str]:
        """استخراج الحقول من Article أو UnifiedArticle."""
        from shared.schemas.unified_article import UnifiedArticle
        from shared.schemas.article import Article

        if isinstance(article, UnifiedArticle):
            return (
                article.id,
                article.title,
                article.content_for_processing(),
                article.url,
            )
        elif isinstance(article, Article):
            return (
                article.id,
                article.title,
                article.content,
                str(article.url),
            )
        else:
            # dict fallback
            return (
                str(article.get("id", "")),
                str(article.get("title", "")),
                str(article.get("content", article.get("cleaned_content", ""))),
                str(article.get("url", "")),
            )

    def _extract_chunk_fields(self, chunk: Any) -> Tuple[str, str, str]:
        """استخراج حقول الـ chunk."""
        from data_engine.processing.transformation.chunking_engine import DocumentChunk
        if isinstance(chunk, DocumentChunk):
            return chunk.chunk_id, chunk.text, chunk.article_id
        elif isinstance(chunk, dict):
            return (
                str(chunk.get("chunk_id", "")),
                str(chunk.get("text", "")),
                str(chunk.get("article_id", "")),
            )
        return "", str(chunk), ""

    def _check_article_duplicate(
        self,
        article_id: str,
        title: str,
        content: str,
        url: str,
        update_state: bool,
    ) -> Optional[str]:
        """فحص مستويات التكرار الثلاثة وإرجاع السبب أو None."""
        cfg = self.config

        # 1. URL hash
        if cfg.deduplicate_urls and url:
            uh = compute_url_hash(url)
            is_dup = uh in self._url_hashes
            if not is_dup and self._store:
                is_dup = self._store.has_article_hash(uh)
            if is_dup:
                return "duplicate_url"
            if update_state:
                self._url_hashes.add(uh)
                if self._store:
                    self._store.add_article_hash(uh, "url", article_id)

        # 2. Content hash
        if cfg.deduplicate_content and content:
            ch = compute_content_hash(title, content, cfg.content_preview_length)
            is_dup = ch in self._content_hashes
            if not is_dup and self._store:
                is_dup = self._store.has_article_hash(ch)
            if is_dup:
                return "duplicate_content"
            if update_state:
                self._content_hashes.add(ch)
                if self._store:
                    self._store.add_article_hash(ch, "content", article_id)

        # 3. Normalized hash (أقوى من content hash)
        nh = compute_normalized_hash(title + content[:200])
        is_dup = False
        # يُفحص فقط في الذاكرة لأنه مكلف في SQLite
        if nh in self._content_hashes:
            return "duplicate_normalized"
        if update_state:
            self._content_hashes.add(nh)

        return None

    def _similarity_dedup(
        self, result: ArticleDedupResult
    ) -> ArticleDedupResult:
        """فحص التشابه النصي بين المقالات الفريدة."""
        threshold = self.config.similarity_threshold
        preview = self.config.content_preview_length
        articles = result.unique_articles
        keep: List[Any] = []
        extra_dups: List[str] = list(result.duplicate_ids)
        pairs: List[Tuple[str, str, float]] = list(result.similarity_pairs)
        dup_set: Set[str] = set(result.duplicate_ids)

        for i, a in enumerate(articles):
            a_id, a_title, a_content, _ = self._extract_article_fields(a)
            if a_id in dup_set:
                continue
            is_dup = False
            for j in range(i):
                b = articles[j]
                b_id, _, b_content, _ = self._extract_article_fields(b)
                if b_id in dup_set:
                    continue
                sim = compute_similarity(
                    a_title + " " + a_content,
                    b_content,
                    preview,
                )
                if sim >= threshold:
                    pairs.append((b_id, a_id, sim))
                    extra_dups.append(a_id)
                    dup_set.add(a_id)
                    result.rejection_reasons[a_id] = f"similar_to:{b_id}:{sim:.2f}"
                    is_dup = True
                    break
            if not is_dup:
                keep.append(a)

        return ArticleDedupResult(
            unique_articles=keep,
            duplicate_ids=extra_dups,
            similarity_pairs=pairs,
            rejection_reasons=result.rejection_reasons,
        )
