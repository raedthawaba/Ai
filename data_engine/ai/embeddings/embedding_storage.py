"""Embedding Storage Schema — Phase 6.5.

يُخزّن الـ embeddings مع كامل بياناتها الوصفية في SQLite.
جاهز للترحيل إلى pgvector أو Qdrant أو FAISS في Phase 7.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_DB_PATH = Path("storage_data/metadata/embeddings.db")


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingRecord — وحدة التخزين
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmbeddingRecord:
    """سجل embedding كامل مع البيانات الوصفية."""

    embedding_id: str
    source_id: str
    source_type: str         # "article" | "chunk"
    model_name: str
    provider: str
    dimensions: int
    vector: List[float]
    token_count: int = 0
    text_preview: str = ""   # أول 200 حرف من النص للمراجعة
    article_id: Optional[str] = None
    chunk_order: Optional[int] = None
    language: str = "en"
    processing_ms: float = 0.0
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "embedding_id": self.embedding_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "model_name": self.model_name,
            "provider": self.provider,
            "dimensions": self.dimensions,
            "token_count": self.token_count,
            "text_preview": self.text_preview,
            "article_id": self.article_id,
            "chunk_order": self.chunk_order,
            "language": self.language,
            "processing_ms": self.processing_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "vector_preview": self.vector[:5],
        }


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingStorage
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingStorage:
    """تخزين الـ embeddings في SQLite مع دعم البحث والاسترجاع.

    Schema مصمم للترحيل السهل إلى pgvector في Phase 7:
    - vector مُخزّن كـ JSON (سيُحوَّل إلى VECTOR في Phase 7)
    - فهرس على source_id و model_name

    Parameters
    ----------
    db_path:
        مسار قاعدة بيانات SQLite.
    """

    def __init__(self, db_path: Path = _STORAGE_DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()
        logger.debug("EmbeddingStorage: جاهز في %s", db_path)

    def _init_schema(self) -> None:
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS embeddings (
                embedding_id  TEXT PRIMARY KEY,
                source_id     TEXT NOT NULL,
                source_type   TEXT NOT NULL DEFAULT 'chunk',
                article_id    TEXT,
                chunk_order   INTEGER,
                model_name    TEXT NOT NULL,
                provider      TEXT NOT NULL DEFAULT 'mock',
                dimensions    INTEGER NOT NULL,
                vector_json   TEXT NOT NULL,
                token_count   INTEGER DEFAULT 0,
                text_preview  TEXT DEFAULT '',
                language      TEXT DEFAULT 'en',
                processing_ms REAL DEFAULT 0.0,
                created_at    TEXT DEFAULT (datetime('now')),
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_emb_source
                ON embeddings(source_id);
            CREATE INDEX IF NOT EXISTS idx_emb_article
                ON embeddings(article_id);
            CREATE INDEX IF NOT EXISTS idx_emb_model
                ON embeddings(model_name);
            CREATE INDEX IF NOT EXISTS idx_emb_source_type
                ON embeddings(source_type);
        """)
        self._db.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, record: EmbeddingRecord) -> str:
        """حفظ سجل embedding."""
        self._db.execute("""
            INSERT OR REPLACE INTO embeddings (
                embedding_id, source_id, source_type, article_id, chunk_order,
                model_name, provider, dimensions, vector_json, token_count,
                text_preview, language, processing_ms, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.embedding_id,
            record.source_id,
            record.source_type,
            record.article_id,
            record.chunk_order,
            record.model_name,
            record.provider,
            record.dimensions,
            json.dumps(record.vector),
            record.token_count,
            record.text_preview[:200],
            record.language,
            record.processing_ms,
            json.dumps(record.metadata),
        ))
        self._db.commit()
        return record.embedding_id

    def save_batch(self, records: List[EmbeddingRecord]) -> int:
        """حفظ دُفعة من الـ embeddings."""
        saved = 0
        for record in records:
            try:
                self.save(record)
                saved += 1
            except Exception as exc:
                logger.error("EmbeddingStorage.save_batch: خطأ — %s", exc)
        logger.info("EmbeddingStorage: حُفظت %d embeddings", saved)
        return saved

    def get(self, embedding_id: str) -> Optional[EmbeddingRecord]:
        """استرجاع سجل بمعرّفه."""
        row = self._db.execute(
            "SELECT * FROM embeddings WHERE embedding_id=?", (embedding_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_source(self, source_id: str) -> List[EmbeddingRecord]:
        """استرجاع جميع embeddings لمصدر معيّن."""
        rows = self._db.execute(
            "SELECT * FROM embeddings WHERE source_id=? ORDER BY chunk_order",
            (source_id,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_by_article(self, article_id: str) -> List[EmbeddingRecord]:
        """استرجاع embeddings مقال كامل."""
        rows = self._db.execute(
            "SELECT * FROM embeddings WHERE article_id=? ORDER BY chunk_order",
            (article_id,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def exists(self, embedding_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM embeddings WHERE embedding_id=?", (embedding_id,)
        ).fetchone()
        return row is not None

    def delete(self, embedding_id: str) -> bool:
        cur = self._db.execute(
            "DELETE FROM embeddings WHERE embedding_id=?", (embedding_id,)
        )
        self._db.commit()
        return cur.rowcount > 0

    def delete_by_article(self, article_id: str) -> int:
        cur = self._db.execute(
            "DELETE FROM embeddings WHERE article_id=?", (article_id,)
        )
        self._db.commit()
        return cur.rowcount

    # ── Stats ─────────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM embeddings"
        ).fetchone()[0]

    def count_by_model(self) -> Dict[str, int]:
        rows = self._db.execute(
            "SELECT model_name, COUNT(*) as cnt FROM embeddings GROUP BY model_name"
        ).fetchall()
        return {row["model_name"]: row["cnt"] for row in rows}

    def stats(self) -> Dict[str, Any]:
        return {
            "total_embeddings": self.count(),
            "by_model": self.count_by_model(),
            "by_type": self._count_by_type(),
        }

    def _count_by_type(self) -> Dict[str, int]:
        rows = self._db.execute(
            "SELECT source_type, COUNT(*) as cnt FROM embeddings GROUP BY source_type"
        ).fetchall()
        return {row["source_type"]: row["cnt"] for row in rows}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> EmbeddingRecord:
        return EmbeddingRecord(
            embedding_id=row["embedding_id"],
            source_id=row["source_id"],
            source_type=row["source_type"],
            model_name=row["model_name"],
            provider=row["provider"],
            dimensions=row["dimensions"],
            vector=json.loads(row["vector_json"]),
            token_count=row["token_count"],
            text_preview=row["text_preview"],
            article_id=row["article_id"],
            chunk_order=row["chunk_order"],
            language=row["language"],
            processing_ms=row["processing_ms"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
