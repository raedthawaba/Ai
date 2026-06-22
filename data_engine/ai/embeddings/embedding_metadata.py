"""Embedding Metadata Tracker — Phase 6.5.

تتبّع البيانات الوصفية لكل عمليات الـ embedding:
  - pipeline runs
  - per-article stats
  - per-chunk stats
  - model performance metrics
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_META_DB_PATH = Path("storage_data/metadata/embedding_metadata.db")


class EmbeddingMetadataTracker:
    """تتبّع تفصيلي لعمليات الـ embedding.

    يُسجّل:
    - كل pipeline run
    - إحصائيات كل مقال
    - أداء النماذج المختلفة
    """

    def __init__(self, db_path: Path = _META_DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id       TEXT PRIMARY KEY,
                article_id   TEXT,
                chunk_count  INTEGER DEFAULT 0,
                embed_count  INTEGER DEFAULT 0,
                model_name   TEXT,
                duration_ms  REAL DEFAULT 0.0,
                errors       INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS article_embedding_stats (
                article_id    TEXT PRIMARY KEY,
                chunk_count   INTEGER DEFAULT 0,
                embed_count   INTEGER DEFAULT 0,
                total_tokens  INTEGER DEFAULT 0,
                model_name    TEXT,
                last_run_id   TEXT,
                created_at    TEXT DEFAULT (datetime('now')),
                updated_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS chunk_embedding_meta (
                chunk_id      TEXT PRIMARY KEY,
                article_id    TEXT,
                embedding_id  TEXT,
                model_name    TEXT,
                token_count   INTEGER DEFAULT 0,
                chunk_order   INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS model_metrics (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name   TEXT NOT NULL,
                provider     TEXT,
                total_calls  INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                avg_ms       REAL DEFAULT 0.0,
                date         TEXT DEFAULT (date('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_runs_article ON pipeline_runs(article_id);
            CREATE INDEX IF NOT EXISTS idx_chunk_article ON chunk_embedding_meta(article_id);
        """)
        self._db.commit()

    def record_pipeline_run(
        self,
        run_id: str,
        article_id: str,
        chunk_count: int,
        embedding_count: int,
        model_name: str,
        duration_ms: float,
        errors: int = 0,
    ) -> None:
        """تسجيل pipeline run."""
        try:
            self._db.execute("""
                INSERT OR REPLACE INTO pipeline_runs
                  (run_id, article_id, chunk_count, embed_count, model_name, duration_ms, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (run_id, article_id, chunk_count, embedding_count,
                  model_name, duration_ms, errors))
            self._db.commit()
        except Exception as exc:
            logger.warning("EmbeddingMeta: خطأ في تسجيل pipeline run — %s", exc)

    def record_article_embeddings(
        self,
        article_id: str,
        chunk_count: int,
        embed_count: int,
        total_tokens: int,
        model_name: str,
        run_id: str,
    ) -> None:
        """تحديث إحصائيات مقال."""
        try:
            self._db.execute("""
                INSERT OR REPLACE INTO article_embedding_stats
                  (article_id, chunk_count, embed_count, total_tokens, model_name, last_run_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (article_id, chunk_count, embed_count, total_tokens, model_name, run_id))
            self._db.commit()
        except Exception as exc:
            logger.warning("EmbeddingMeta: خطأ في تسجيل إحصائيات مقال — %s", exc)

    def record_chunk_embedding(
        self,
        chunk_id: str,
        article_id: str,
        embedding_id: str,
        model_name: str,
        token_count: int,
        chunk_order: int,
    ) -> None:
        """تسجيل embedding لـ chunk."""
        try:
            self._db.execute("""
                INSERT OR REPLACE INTO chunk_embedding_meta
                  (chunk_id, article_id, embedding_id, model_name, token_count, chunk_order)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chunk_id, article_id, embedding_id, model_name, token_count, chunk_order))
            self._db.commit()
        except Exception as exc:
            logger.warning("EmbeddingMeta: خطأ في تسجيل chunk — %s", exc)

    def get_article_stats(self, article_id: str) -> Optional[Dict[str, Any]]:
        """إحصائيات مقال."""
        row = self._db.execute(
            "SELECT * FROM article_embedding_stats WHERE article_id=?",
            (article_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_pipeline_runs(
        self,
        article_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """استرجاع pipeline runs."""
        if article_id:
            rows = self._db.execute(
                "SELECT * FROM pipeline_runs WHERE article_id=? ORDER BY created_at DESC LIMIT ?",
                (article_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def overall_stats(self) -> Dict[str, Any]:
        """إحصائيات عامة."""
        total_runs = self._db.execute(
            "SELECT COUNT(*) FROM pipeline_runs"
        ).fetchone()[0]
        total_articles = self._db.execute(
            "SELECT COUNT(*) FROM article_embedding_stats"
        ).fetchone()[0]
        total_chunks = self._db.execute(
            "SELECT COUNT(*) FROM chunk_embedding_meta"
        ).fetchone()[0]
        total_tokens = self._db.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) FROM article_embedding_stats"
        ).fetchone()[0]

        return {
            "pipeline_runs": total_runs,
            "articles_embedded": total_articles,
            "chunks_embedded": total_chunks,
            "total_tokens": total_tokens,
        }
