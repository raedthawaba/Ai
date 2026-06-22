"""Metadata Tracker — Phase 6.5.

سجل مركزي لجميع البيانات الوصفية في النظام:
  - Article: معلومات المقال عبر مراحل المعالجة
  - Chunk: معلومات كل قطعة نصية
  - Embedding: معلومات الـ embedding
  - Pipeline Stage: إحصائيات كل مرحلة في الـ pipeline

يُخزّن في SQLite ويُتيح استعلامات مرنة.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

_META_DB_PATH = Path("storage_data/metadata/system_metadata.db")


# ─────────────────────────────────────────────────────────────────────────────
# Records
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArticleMetadataRecord:
    """سجل البيانات الوصفية لمقال."""

    article_id: str
    source_id: str
    source_type: str = "rss"
    language: str = "en"
    title: str = ""
    url: str = ""
    word_count: int = 0
    char_count: int = 0
    has_summary: bool = False
    keyword_count: int = 0
    entity_count: int = 0
    chunk_count: int = 0
    embedding_id: Optional[str] = None
    processing_stage: str = "raw"   # raw | bronze | silver | gold | embedded
    content_hash: Optional[str] = None
    url_hash: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    pipeline_run_id: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkMetadataRecord:
    """سجل البيانات الوصفية لـ chunk."""

    chunk_id: str
    article_id: str
    order: int
    char_count: int
    token_count: int
    strategy: str = "recursive"
    content_hash: str = ""
    is_duplicate: bool = False
    embedding_id: Optional[str] = None
    language: str = "en"
    created_at: datetime = field(default_factory=utc_now)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingMetaRecord:
    """سجل البيانات الوصفية لـ embedding."""

    embedding_id: str
    source_id: str
    source_type: str      # "article" | "chunk"
    article_id: Optional[str]
    model_name: str
    provider: str
    dimensions: int
    token_count: int = 0
    processing_ms: float = 0.0
    created_at: datetime = field(default_factory=utc_now)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineStageRecord:
    """سجل إحصائيات مرحلة pipeline."""

    run_id: str
    stage_name: str
    input_count: int
    output_count: int
    rejected_count: int
    error_count: int
    duration_ms: float
    source_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


# ─────────────────────────────────────────────────────────────────────────────
# MetadataTracker
# ─────────────────────────────────────────────────────────────────────────────

class MetadataTracker:
    """سجل مركزي شامل لجميع بيانات النظام الوصفية.

    يوفر:
    - تسجيل البيانات الوصفية لكل مستوى (article/chunk/embedding/stage)
    - استعلامات مرنة
    - إحصائيات عامة
    - تتبّع تدفق البيانات عبر المراحل

    Parameters
    ----------
    db_path:
        مسار قاعدة بيانات SQLite.
    """

    def __init__(self, db_path: Path = _META_DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()
        logger.debug("MetadataTracker: جاهز في %s", db_path)

    def _init_schema(self) -> None:
        self._db.executescript("""
            -- بيانات المقالات
            CREATE TABLE IF NOT EXISTS article_metadata (
                article_id       TEXT PRIMARY KEY,
                source_id        TEXT NOT NULL,
                source_type      TEXT DEFAULT 'rss',
                language         TEXT DEFAULT 'en',
                title            TEXT DEFAULT '',
                url              TEXT DEFAULT '',
                word_count       INTEGER DEFAULT 0,
                char_count       INTEGER DEFAULT 0,
                has_summary      INTEGER DEFAULT 0,
                keyword_count    INTEGER DEFAULT 0,
                entity_count     INTEGER DEFAULT 0,
                chunk_count      INTEGER DEFAULT 0,
                embedding_id     TEXT,
                processing_stage TEXT DEFAULT 'raw',
                content_hash     TEXT,
                url_hash         TEXT,
                is_duplicate     INTEGER DEFAULT 0,
                duplicate_of     TEXT,
                pipeline_run_id  TEXT,
                created_at       TEXT DEFAULT (datetime('now')),
                updated_at       TEXT DEFAULT (datetime('now')),
                extra_json       TEXT DEFAULT '{}'
            );

            -- بيانات الـ chunks
            CREATE TABLE IF NOT EXISTS chunk_metadata (
                chunk_id      TEXT PRIMARY KEY,
                article_id    TEXT NOT NULL,
                ord           INTEGER DEFAULT 0,
                char_count    INTEGER DEFAULT 0,
                token_count   INTEGER DEFAULT 0,
                strategy      TEXT DEFAULT 'recursive',
                content_hash  TEXT DEFAULT '',
                is_duplicate  INTEGER DEFAULT 0,
                embedding_id  TEXT,
                language      TEXT DEFAULT 'en',
                created_at    TEXT DEFAULT (datetime('now')),
                extra_json    TEXT DEFAULT '{}'
            );

            -- بيانات الـ embeddings
            CREATE TABLE IF NOT EXISTS embedding_metadata (
                embedding_id  TEXT PRIMARY KEY,
                source_id     TEXT NOT NULL,
                source_type   TEXT DEFAULT 'chunk',
                article_id    TEXT,
                model_name    TEXT NOT NULL,
                provider      TEXT DEFAULT 'mock',
                dimensions    INTEGER NOT NULL,
                token_count   INTEGER DEFAULT 0,
                processing_ms REAL DEFAULT 0.0,
                created_at    TEXT DEFAULT (datetime('now')),
                extra_json    TEXT DEFAULT '{}'
            );

            -- إحصائيات مراحل الـ pipeline
            CREATE TABLE IF NOT EXISTS pipeline_stage_metadata (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        TEXT NOT NULL,
                stage_name    TEXT NOT NULL,
                input_count   INTEGER DEFAULT 0,
                output_count  INTEGER DEFAULT 0,
                rejected_count INTEGER DEFAULT 0,
                error_count   INTEGER DEFAULT 0,
                duration_ms   REAL DEFAULT 0.0,
                source_id     TEXT DEFAULT '',
                created_at    TEXT DEFAULT (datetime('now')),
                extra_json    TEXT DEFAULT '{}'
            );

            -- فهارس
            CREATE INDEX IF NOT EXISTS idx_art_source ON article_metadata(source_id);
            CREATE INDEX IF NOT EXISTS idx_art_stage  ON article_metadata(processing_stage);
            CREATE INDEX IF NOT EXISTS idx_art_dup    ON article_metadata(is_duplicate);
            CREATE INDEX IF NOT EXISTS idx_chk_article ON chunk_metadata(article_id);
            CREATE INDEX IF NOT EXISTS idx_emb_source  ON embedding_metadata(source_id);
            CREATE INDEX IF NOT EXISTS idx_stage_run   ON pipeline_stage_metadata(run_id);
        """)
        self._db.commit()

    # ─────────────────────────────────────────────────────────────────────────
    # Article
    # ─────────────────────────────────────────────────────────────────────────

    def track_article(self, record: ArticleMetadataRecord) -> None:
        """تسجيل/تحديث بيانات مقال."""
        try:
            self._db.execute("""
                INSERT OR REPLACE INTO article_metadata (
                    article_id, source_id, source_type, language, title, url,
                    word_count, char_count, has_summary, keyword_count, entity_count,
                    chunk_count, embedding_id, processing_stage, content_hash, url_hash,
                    is_duplicate, duplicate_of, pipeline_run_id, updated_at, extra_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?)
            """, (
                record.article_id, record.source_id, record.source_type,
                record.language, record.title, record.url,
                record.word_count, record.char_count, int(record.has_summary),
                record.keyword_count, record.entity_count, record.chunk_count,
                record.embedding_id, record.processing_stage,
                record.content_hash, record.url_hash,
                int(record.is_duplicate), record.duplicate_of,
                record.pipeline_run_id, json.dumps(record.extra),
            ))
            self._db.commit()
        except Exception as exc:
            logger.warning("MetadataTracker.track_article: %s — %s", record.article_id, exc)

    def track_articles_bulk(self, records: List[ArticleMetadataRecord]) -> int:
        """تسجيل دُفعة من المقالات."""
        saved = 0
        for rec in records:
            try:
                self.track_article(rec)
                saved += 1
            except Exception:
                pass
        return saved

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM article_metadata WHERE article_id=?", (article_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_article_stage(
        self, article_id: str, stage: str, **updates: Any
    ) -> None:
        """تحديث مرحلة معالجة المقال."""
        set_parts = ["processing_stage=?", "updated_at=datetime('now')"]
        values = [stage]
        for key, val in updates.items():
            set_parts.append(f"{key}=?")
            values.append(val)
        values.append(article_id)
        self._db.execute(
            f"UPDATE article_metadata SET {', '.join(set_parts)} WHERE article_id=?",
            values,
        )
        self._db.commit()

    # ─────────────────────────────────────────────────────────────────────────
    # Chunk
    # ─────────────────────────────────────────────────────────────────────────

    def track_chunk(self, record: ChunkMetadataRecord) -> None:
        """تسجيل بيانات chunk."""
        try:
            self._db.execute("""
                INSERT OR REPLACE INTO chunk_metadata (
                    chunk_id, article_id, ord, char_count, token_count,
                    strategy, content_hash, is_duplicate, embedding_id, language, extra_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                record.chunk_id, record.article_id, record.order,
                record.char_count, record.token_count, record.strategy,
                record.content_hash, int(record.is_duplicate),
                record.embedding_id, record.language, json.dumps(record.extra),
            ))
            self._db.commit()
        except Exception as exc:
            logger.warning("MetadataTracker.track_chunk: %s — %s", record.chunk_id, exc)

    def track_chunks_bulk(self, records: List[ChunkMetadataRecord]) -> int:
        saved = 0
        for rec in records:
            try:
                self.track_chunk(rec)
                saved += 1
            except Exception:
                pass
        return saved

    def get_chunks_for_article(self, article_id: str) -> List[Dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM chunk_metadata WHERE article_id=? ORDER BY ord",
            (article_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    # Embedding
    # ─────────────────────────────────────────────────────────────────────────

    def track_embedding(self, record: EmbeddingMetaRecord) -> None:
        """تسجيل بيانات embedding."""
        try:
            self._db.execute("""
                INSERT OR REPLACE INTO embedding_metadata (
                    embedding_id, source_id, source_type, article_id,
                    model_name, provider, dimensions, token_count, processing_ms, extra_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                record.embedding_id, record.source_id, record.source_type,
                record.article_id, record.model_name, record.provider,
                record.dimensions, record.token_count, record.processing_ms,
                json.dumps(record.extra),
            ))
            self._db.commit()
        except Exception as exc:
            logger.warning("MetadataTracker.track_embedding: %s — %s", record.embedding_id, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline Stage
    # ─────────────────────────────────────────────────────────────────────────

    def track_stage(self, record: PipelineStageRecord) -> None:
        """تسجيل إحصائيات مرحلة pipeline."""
        try:
            self._db.execute("""
                INSERT INTO pipeline_stage_metadata (
                    run_id, stage_name, input_count, output_count,
                    rejected_count, error_count, duration_ms, source_id, extra_json
                ) VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                record.run_id, record.stage_name, record.input_count,
                record.output_count, record.rejected_count, record.error_count,
                record.duration_ms, record.source_id, json.dumps(record.extra),
            ))
            self._db.commit()
        except Exception as exc:
            logger.warning("MetadataTracker.track_stage: %s — %s", record.stage_name, exc)

    def track_pipeline_run(
        self,
        run_id: str,
        source_id: str,
        stage_traces: List[Any],
    ) -> None:
        """تسجيل كامل pipeline run من ProcessingContext traces."""
        for trace in stage_traces:
            self.track_stage(PipelineStageRecord(
                run_id=run_id,
                stage_name=trace.stage_name,
                input_count=trace.input_count,
                output_count=trace.output_count,
                rejected_count=trace.rejected_count,
                error_count=trace.error_count,
                duration_ms=trace.duration_ms,
                source_id=source_id,
            ))

    def get_stage_stats_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM pipeline_stage_metadata WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    # Overall Stats
    # ─────────────────────────────────────────────────────────────────────────

    def overall_stats(self) -> Dict[str, Any]:
        """إحصائيات شاملة للنظام."""
        art_total = self._db.execute(
            "SELECT COUNT(*) FROM article_metadata"
        ).fetchone()[0]
        art_dups = self._db.execute(
            "SELECT COUNT(*) FROM article_metadata WHERE is_duplicate=1"
        ).fetchone()[0]
        chunk_total = self._db.execute(
            "SELECT COUNT(*) FROM chunk_metadata"
        ).fetchone()[0]
        emb_total = self._db.execute(
            "SELECT COUNT(*) FROM embedding_metadata"
        ).fetchone()[0]
        stage_runs = self._db.execute(
            "SELECT COUNT(DISTINCT run_id) FROM pipeline_stage_metadata"
        ).fetchone()[0]

        # توزيع المراحل
        stage_dist = {}
        rows = self._db.execute(
            "SELECT processing_stage, COUNT(*) as cnt "
            "FROM article_metadata GROUP BY processing_stage"
        ).fetchall()
        for row in rows:
            stage_dist[row["processing_stage"]] = row["cnt"]

        # توزيع اللغات
        lang_dist = {}
        rows = self._db.execute(
            "SELECT language, COUNT(*) as cnt "
            "FROM article_metadata GROUP BY language"
        ).fetchall()
        for row in rows:
            lang_dist[row["language"]] = row["cnt"]

        return {
            "articles": {
                "total": art_total,
                "duplicates": art_dups,
                "unique": art_total - art_dups,
                "by_stage": stage_dist,
                "by_language": lang_dist,
            },
            "chunks": {"total": chunk_total},
            "embeddings": {"total": emb_total},
            "pipeline": {"total_runs": stage_runs},
        }

    def articles_by_source(self, source_id: str) -> List[Dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM article_metadata WHERE source_id=? ORDER BY created_at DESC",
            (source_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def duplicate_articles(self) -> List[Dict[str, Any]]:
        rows = self._db.execute(
            "SELECT article_id, duplicate_of, content_hash "
            "FROM article_metadata WHERE is_duplicate=1"
        ).fetchall()
        return [dict(r) for r in rows]

    def pipeline_performance(self) -> Dict[str, Any]:
        """متوسط أداء كل مرحلة pipeline."""
        rows = self._db.execute("""
            SELECT stage_name,
                   COUNT(*) as runs,
                   AVG(duration_ms) as avg_ms,
                   SUM(input_count) as total_in,
                   SUM(output_count) as total_out,
                   SUM(rejected_count) as total_rejected
            FROM pipeline_stage_metadata
            GROUP BY stage_name
        """).fetchall()

        stages = {}
        for row in rows:
            stages[row["stage_name"]] = {
                "runs": row["runs"],
                "avg_ms": round(row["avg_ms"] or 0, 2),
                "total_in": row["total_in"],
                "total_out": row["total_out"],
                "rejection_rate": round(
                    row["total_rejected"] / row["total_in"], 3
                ) if row["total_in"] else 0.0,
            }
        return stages
